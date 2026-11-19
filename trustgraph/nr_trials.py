"""Train the existing graph/GRU architecture on recorded NR co-simulation runs."""
import argparse
from bisect import bisect_right
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import numpy as np
import torch
from torch.utils.data import DataLoader

from .learning import binary_metrics, evaluate, seed_everything
from .model import TrustGraph, multitask_loss


HISTORY = 10
HORIZON = 10
LIMIT_DB = 40.0
LOAD_SCALE = 0.1
CELL_X = np.array([250, 750], dtype=np.float32)
MAX_CARS = 4
VESSEL = re.compile(r'TRUSTGRAPH_VEHICLE car\[(\d+)\] (trust-\d+)')
BEACON = re.compile(r'UE (\d+) broadcast frame from ([12]) with RSSI: (\S+) at (\S+)')


def aligned_trial(directory):
    """Load one completed run on the 100 ms availability grid."""
    meta = json.loads((directory / 'trial.json').read_text())
    log = (directory / 'run.log').read_text()
    if 'Simulation time limit reached -- at t=35s' not in log:
        raise ValueError(f'Incomplete simulation {directory}')
    count = meta['cars']
    vehicles = dict((int(index), name) for index, name in VESSEL.findall(log))
    if set(vehicles) != set(range(count)) or len(set(vehicles.values())) != count:
        raise ValueError(f'Invalid Veins vehicle mapping in {directory}')
    values = {}
    vectors = {}
    with (directory / 'handover.vec').open() as stream:
        for line in stream:
            if line.startswith('vector '):
                _, vector, module, name, columns = line.split()
                if columns != 'ETV':
                    raise ValueError('Expected event, time and value columns')
                vectors[vector] = (module, name)
            elif line and line[0].isdigit():
                vector, _, time, value = line.split()
                values.setdefault(vectors[vector], []).append((float(time), float(value)))

    times = np.arange(1, 351) / 10
    motion = np.full((350, count, 3), np.nan, dtype=np.float32)
    by_id = {name: index for index, name in vehicles.items()}
    for timestep in ET.parse(directory / 'sumo-fcd.xml').iter('timestep'):
        tick = round(float(timestep.attrib['time']) * 10)
        if tick >= len(times):
            break
        for car in timestep.findall('vehicle'):
            motion[tick, by_id[car.attrib['id']]] = [
                float(car.attrib[key]) for key in ('x', 'y', 'speed')]
    if not np.isfinite(motion).all():
        raise ValueError(f'Missing vehicle positions in {directory}')

    scalar = (directory / 'handover.sca').read_text()
    ue_indexes = {int(ue): int(index) for index, ue in re.findall(
        r'^par TrustGraphRoad\.car\[(\d+)\]\.cellularNic\.rrc\.nrConnectionControl macNodeId (\d+)$',
        scalar, re.MULTILINE)}
    if set(ue_indexes.values()) != set(vehicles):
        raise ValueError(f'Missing NR vehicle identity in {directory}')
    associations = {}
    for index in range(count):
        module = f'TrustGraphRoad.car[{index}].mobility'
        for axis, origin, orientation in (('X', 25, 1), ('Y', 25, -1)):
            coordinates = values[(module, f'sumo{axis}')]
            expected = motion[1:, index, 0 if axis == 'X' else 1] * orientation + origin
            if (len(coordinates) != len(expected)
                or not np.allclose([time for time, _ in coordinates], times[1:])
                or not np.allclose([value for _, value in coordinates], expected, atol=0.02, rtol=0)):
                raise ValueError(f'SUMO and NR position mismatch for car[{index}] in {directory}')
    for (module, name), points in values.items():
        if name == 'servingCell:vector' and module.endswith('.nrConnectionControl'):
            index = int(re.search(r'\.car\[(\d+)\]', module)[1])
            associations[index] = sorted(points)
    if set(associations) != set(vehicles):
        raise ValueError(f'Missing serving-cell trace in {directory}')
    serving = np.column_stack([
        np.array([points[bisect_right(points, (time, float('inf'))) - 1][1] - 1
                  if time >= points[0][0] else -1 for time in times], dtype=np.int64)
        for points in (associations[index] for index in range(count))
    ])
    candidates = np.full((350, count, 2), np.nan, dtype=np.float32)
    for ue, gnb, db, time in BEACON.findall(log):
        index, tick = ue_indexes[int(ue)], round(float(time) * 10) - 1
        if not 0 <= index < count or not 0 <= tick < len(times):
            raise ValueError(f'Unexpected beacon identity or timestamp in {directory}')
        candidates[tick, index, int(gnb) - 1] = float(db)
    if not np.isfinite(candidates).any(axis=0).all():
        raise ValueError(f'Missing candidate measurements in {directory}')
    fresh = candidates.copy()
    for index in range(1, len(times)):
        candidates[index] = np.where(np.isfinite(candidates[index]), candidates[index], candidates[index - 1])
    load = []
    for gnb in (1, 2):
        samples = values[(f'TrustGraphRoad.gnb{gnb}.cellularNic.mac', 'avgServedBlocksDl:vector')]
        if len(samples) != 35000 or not np.allclose([time for time, _ in samples], np.arange(1, 35001) / 1000):
            raise ValueError(f'Incomplete MAC slot statistics in {directory}')
        capacity = meta.get('blocks_per_slot', 50)
        if capacity <= 0 or any(not 0 <= blocks <= capacity for _, blocks in samples):
            raise ValueError(f'Invalid MAC capacity or allocation in {directory}')
        load.append(np.asarray([blocks for _, blocks in samples]).reshape(350, 100).mean(axis=1) / capacity)
    return meta, motion, serving, candidates, fresh, np.asarray(load, dtype=np.float32).T


def graph_features(motion, serving, radio, load, load_scale=LOAD_SCALE):
    """Encode reported motion, observed beacons and measured MAC load."""
    x, y, speed = motion.transpose(2, 0, 1)
    longitudinal = np.diff(x, axis=0, prepend=x[:1]) / 0.1
    residual = np.abs(np.abs(longitudinal) - speed)
    residual[0] = 0
    safe_serving = serving.clip(min=0)
    current = np.take_along_axis(radio, safe_serving[..., None], axis=2)[..., 0]
    edge_mask = np.isfinite(radio) & (serving[..., None] >= 0)
    scaled = np.nan_to_num(radio / 100, nan=0)
    vehicle = np.stack([x / 1200, y / 20, speed / 24, np.clip(longitudinal / 24, -2, 2),
                        np.clip(residual / 24, 0, 5), np.nan_to_num(current / 100),
                        np.isfinite(current)], axis=-1)
    cell = np.stack([np.broadcast_to(CELL_X / 1200, load.shape), load / load_scale], axis=-1)
    edge = np.stack([scaled, abs(x[..., None] + 25 - CELL_X) / 1200,
                     safe_serving[..., None] == np.arange(2)], axis=-1)
    return dict(vehicle=vehicle.astype('float32'), cell=cell.astype('float32'),
                edge=edge.astype('float32'), edge_mask=edge_mask.astype('float32'))


def sequence_data(directory, load_scale=LOAD_SCALE, max_cars=MAX_CARS):
    meta, motion, serving, radio, fresh, load = aligned_trial(directory)
    actual = meta['cars']
    if actual > max_cars:
        raise ValueError(f'{directory} has {actual} cars but this dataset supports {max_cars}')
    rng = np.random.default_rng(meta['seed'])
    examples = []
    for corrupt in (False, True):
        reported = motion.copy()
        attack = np.zeros(serving.shape, dtype=np.float32)
        if corrupt:
            for index in rng.choice(actual, size=max(1, actual // 2), replace=False):
                start = int(rng.integers(40, 115))
                end = min(len(reported), start + int(rng.integers(75, 180)))
                attack[start:end, index] = 1
                reported[start:end, index, 0] += rng.choice([-1, 1]) * rng.uniform(50, 180)
                reported[start:end, index, 0] += rng.normal(0, 4, end - start)
        graphs = graph_features(reported, serving, radio, load, load_scale)
        for end in range(HISTORY - 1, len(motion) - HORIZON, 2):
            start = end - HISTORY + 1
            future = serving[end + 1:end + HORIZON + 1]
            valid_cell = serving[end].clip(min=0)
            upcoming = fresh[end + 1:end + HORIZON + 1, np.arange(actual), valid_cell]
            valid = (future == serving[end]).all(0) & (serving[end] >= 0) & np.isfinite(upcoming).any(0)
            risk = (upcoming < LIMIT_DB).any(0)
            graph = {}
            for key, value in graphs.items():
                window = value[start:end + 1]
                if key != 'cell':
                    padding = [(0, 0)] * window.ndim
                    padding[1] = (0, max_cars - actual)
                    window = np.pad(window, padding)
                graph[key] = torch.tensor(window)
            graph['vehicle'][0, :, 3:5] = 0
            def pad(values):
                return torch.from_numpy(np.pad(values.astype(np.float32), (0, max_cars - actual)))
            examples.append((graph, dict(risk=pad(risk), risk_mask=pad(valid),
                                         attack=pad(attack[end]), vehicle_mask=pad(np.ones(actual)),
                                         load=torch.from_numpy(load[end + HORIZON] / load_scale))))
    return meta, examples


@torch.no_grad()
def load_forecasts(model, loader, blend=1., smooth=False):
    currents, predictions, targets = [], [], []
    if model is not None:
        model.eval()
        model.load_blend = blend
    for graph, target in loader:
        current = graph['cell'][:, -1, :, 1]
        currents.append(current.numpy())
        baseline = graph['cell'][:, -5:, :, 1].mean(dim=1) if smooth else current
        predictions.append(baseline.numpy() if model is None else model(graph)['load'].numpy())
        targets.append(target['load'].numpy())
    current, predicted, target = map(np.concatenate, (currents, predictions, targets))
    error = predicted - target
    busy = (current > 0.8) | (target > 0.8)
    def metrics(values):
        return {'count': int(values.size), 'mae': float(np.abs(values).mean()) if values.size else None,
                'rmse': float(np.sqrt(np.square(values).mean())) if values.size else None}
    return {'all': metrics(error), 'congested': metrics(error[busy])}


def train_models(batch, output, congestion=False):
    seed_everything(2026)
    suites = {split: [] for split in ('train', 'validation', 'test')}
    metadata = []
    held_out = {}
    scale = 1. if congestion else LOAD_SCALE
    for directory in sorted(batch.glob('trial-*')):
        meta, examples = sequence_data(directory, scale, 8 if congestion else MAX_CARS)
        suites[meta['split']].extend(examples)
        metadata.append(meta)
        if meta['split'] == 'test':
            held_out[meta['id']] = DataLoader(examples, batch_size=64)
        print(f'{meta["id"]}: {meta["cars"]} cars, {len(examples)} windows', flush=True)
    if any(not suite for suite in suites.values()):
        raise ValueError('All three run splits must contain examples')
    output.mkdir(parents=True, exist_ok=True)
    metrics = {}
    loaders = {k: DataLoader(v, batch_size=64, shuffle=k == 'train') for k, v in suites.items()}
    labels = torch.cat([target['risk'][target['risk_mask'].bool()] for _, target in suites['train']])
    if labels.numel() == 0 or labels.unique().numel() < 2:
        raise ValueError('Training needs both degraded and healthy NR windows')
    weights = {'risk': min(20., float((1 - labels).sum() / labels.sum())), 'attack': 1.}
    validation_baseline = load_forecasts(None, loaders['validation']) if congestion else None
    for aware in (False, True):
        seed_everything(2026)
        name = 'trustgraph' if aware else 'graph_without_trust'
        model = TrustGraph(32, aware, residual_load=congestion)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.003)
        best = (True, float('inf'))
        path = output / f'{name}.pt'
        for epoch in range(16 if congestion else 12):
            model.train()
            model.load_blend = 1.
            for graph, target in loaders['train']:
                optimizer.zero_grad()
                current_load = graph['cell'][:, -1, :, 1] if congestion else None
                loss = multitask_loss(model(graph), target, weights, load_weight=12. if congestion else 1.,
                                      current_load=current_load)
                loss.backward()
                optimizer.step()
            blend = 1.
            if congestion:
                # Select only on validation. Zero correction is the simple
                # trailing 500 ms mean, reported separately on the test split.
                candidates = []
                for value in (0., 0.25, 0.5, 1.):
                    result = load_forecasts(model, loaders['validation'], value)
                    differences = [result[group]['mae'] - baseline['mae']
                                   for group, baseline in validation_baseline.items() if baseline['count']]
                    candidates.append(((max(differences) >= 0, sum(differences)), value))
                criterion, blend = min(candidates)
            else:
                criterion = (False, evaluate(model, loaders['validation'], weights)['loss'])
            if criterion < best:
                best = criterion
                torch.save({'source': 'SUMO/Veins/Simu5G', 'state_dict': model.state_dict(),
                            'trust_aware': aware, 'history': HISTORY, 'hidden': 32,
                            'residual_load': congestion, 'load_scale': scale, 'load_blend': blend,
                            'epoch': epoch + 1}, path)
        checkpoint = torch.load(path, weights_only=True)
        model.load_state_dict(checkpoint['state_dict'])
        model.load_blend = checkpoint['load_blend']
        result = evaluate(model, loaders['test'], weights)
        result['load'] = {k: value * scale for k, value in result['load'].items()}
        if congestion:
            result['forecast'] = load_forecasts(model, loaders['test'], checkpoint['load_blend'])
            result['forecast_by_run'] = {key: load_forecasts(model, loader, checkpoint['load_blend'])
                                         for key, loader in held_out.items()}
            result['selected_blend'] = checkpoint['load_blend']
        metrics[name] = result
        print(name, json.dumps(result), flush=True)
    risk_y, risk_score, attack_y, attack_score, errors = [], [], [], [], []
    for graph, target in loaders['test']:
        mask = target['risk_mask'].bool()
        active = target['vehicle_mask'].bool()
        risk_y.extend(target['risk'][mask].numpy())
        risk_score.extend(torch.sigmoid((LIMIT_DB - 100 * graph['vehicle'][:, -1, :, 5][mask]) / 5).numpy())
        attack_y.extend(target['attack'][active].numpy())
        attack_score.extend(torch.sigmoid((24 * graph['vehicle'][:, -1, :, 4][active] - 8) / 3).numpy())
        errors.extend((scale * (graph['cell'][:, -1, :, 1] - target['load'])).numpy().ravel())
    metrics['fixed_rules'] = dict(link=binary_metrics(risk_y, risk_score),
                                  attack=binary_metrics(attack_y, attack_score),
                                  load=dict(mae=float(np.mean(np.abs(errors))),
                                            rmse=float(np.sqrt(np.mean(np.square(errors))))))
    report = dict(source='SUMO/Veins/Simu5G', trials=metadata, metrics=metrics,
                  window_counts={name: len(items) for name, items in suites.items()},
                  horizon_seconds=1., beacon_degradation_threshold_db=LIMIT_DB)
    if congestion:
        persistence = load_forecasts(None, loaders['test'])
        learned = metrics['trustgraph']['forecast']
        report['persistence'] = persistence
        report['trailing_mean'] = load_forecasts(None, loaders['test'], smooth=True)
        report['persistence_by_run'] = {key: load_forecasts(None, loader) for key, loader in held_out.items()}
        report['passed_forecast_gate'] = (
            learned['congested']['mae'] is not None
            and learned['congested']['mae'] < persistence['congested']['mae']
            and learned['all']['mae'] < persistence['all']['mae'])
    (output / 'metrics.json').write_text(json.dumps(report, indent=2, allow_nan=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--congestion', action='store_true')
    args = parser.parse_args()
    train_models(args.batch, args.output, args.congestion)
