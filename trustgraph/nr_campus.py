"""Train and run TrustGraph on the synchronized four-cell NITK traces."""

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import time

import numpy as np
import torch
from torch.utils.data import DataLoader

from .learning import seed_everything
from .model import TrustGraph, multitask_loss


HISTORY = 10
HORIZON = 20
BEACON = re.compile(r'UE (\d+) broadcast frame from (\d+) with RSSI: (\S+) at (\S+)')
OBS = re.compile(r'TRUSTGRAPH_CAMPUS ([^\r\n]+)')


@dataclass
class Trace:
    ticks: np.ndarray
    ids: list[int]
    motion: np.ndarray
    serving: np.ndarray
    radio: np.ndarray
    fresh: np.ndarray
    load: np.ndarray


def read_trace(log, cells, now=float('inf')):
    rows = {}
    for match in OBS.findall(log):
        fields = match.split()
        if len(fields) != 6 + cells:
            raise ValueError('Invalid campus telemetry row')
        tick, ue = map(int, fields[:2])
        # Veins reports initial radio modules before the first real road position.
        if tick >= 2 and tick / 10 + 0.000001 <= now + 1e-9:
            rows.setdefault(tick, {})[ue] = list(map(float, fields[2:]))
    ticks = np.array(sorted(rows), dtype=int)
    if not ticks.size:
        return None
    ids = sorted(rows[ticks[-1]])
    if np.any(np.diff(ticks) != 1) or any(sorted(rows[tick]) != ids for tick in ticks):
        return None
    values = np.array([[rows[tick][ue] for ue in ids] for tick in ticks], dtype=np.float32)
    ue_index = {ue: index for index, ue in enumerate(ids)}
    fresh = np.full((len(ticks), len(ids), cells), np.nan, dtype=np.float32)
    for ue, cell, db, stamp in BEACON.findall(log):
        ue, cell, stamp = int(ue), int(cell), float(stamp)
        tick = round(stamp * 10) - ticks[0]
        if ue in ue_index and 1 <= cell <= cells and 0 <= tick < len(ticks) and stamp <= now:
            fresh[tick, ue_index[ue], cell - 1] = float(db)
    radio = fresh.copy()
    for i in range(1, len(ticks)):
        radio[i] = np.where(np.isfinite(radio[i]), radio[i], radio[i - 1])
    return Trace(ticks, ids, values[..., :3], values[..., 3].astype(int) - 1, radio, fresh, values[:, 0, 4:])


def features(motion, serving, radio, load, towers):
    center = towers.mean(axis=0)
    xy = motion[..., :2]
    speed = motion[..., 2]
    velocity = np.diff(xy, axis=0, prepend=xy[:1]) / 0.1
    residual = abs(np.linalg.norm(velocity, axis=-1) - speed)
    residual[0] = 0
    current = np.take_along_axis(radio, serving.clip(min=0)[..., None], axis=2)[..., 0]
    vehicle = np.stack([(xy[..., 0] - center[0]) / 1200, (xy[..., 1] - center[1]) / 1200,
                        speed / 24, np.clip(velocity[..., 1] / 24, -2, 2),
                        np.clip(residual / 24, 0, 5), np.nan_to_num(current / 100), np.isfinite(current)], axis=-1)
    cell = np.stack([np.broadcast_to((towers[:, 1] - center[1]) / 1200, load.shape), load], axis=-1)
    distance = np.linalg.norm(xy[..., None, :] - towers, axis=-1)
    edge = np.stack([np.nan_to_num(radio / 100), distance / 1200,
                     serving[..., None] == np.arange(len(towers))], axis=-1)
    mask = np.isfinite(radio) & (serving[..., None] >= 0)
    return {key: torch.from_numpy(value.astype('float32')) for key, value in
            dict(vehicle=vehicle, cell=cell, edge=edge, edge_mask=mask).items()}


def load_examples(directory):
    meta = json.loads((directory / 'campus-meta.json').read_text())
    towers = np.asarray(meta['towers'], dtype=np.float32)
    log = (directory / 'run.log').read_text(encoding='utf-8')
    trace = read_trace(log, len(towers))
    if trace is None or trace.ticks[-1] < 349 or len(trace.ids) != 8 or len(towers) != 4:
        raise ValueError(f'Incomplete four-cell trace in {directory}')
    rng = np.random.default_rng(meta['seed'])
    examples = []
    for corrupt in (False, True):
        reported = trace.motion.copy()
        attack = np.zeros(trace.serving.shape, dtype=np.float32)
        if corrupt:
            for vehicle in rng.choice(len(trace.ids), size=3, replace=False):
                start = rng.integers(30, 120)
                finish = start + rng.integers(80, 150)
                reported[start:finish, vehicle, 0] += rng.uniform(65, 160) * rng.choice([-1, 1])
                reported[start:finish, vehicle, 0] += rng.normal(0, 4, size=finish - start)
                attack[start:finish, vehicle] = 1
        graph = features(reported, trace.serving, trace.radio, trace.load, towers)
        for end in range(HISTORY - 1, len(trace.ticks) - HORIZON, 5):
            start = end - HISTORY + 1
            window = {key: value[start:end + 1] for key, value in graph.items()}
            window['vehicle'] = window['vehicle'].clone()
            window['vehicle'][0, :, 3:5] = 0
            upcoming = trace.fresh[end + 1:end + HORIZON + 1]
            count = np.isfinite(upcoming).sum(axis=0)
            radio = np.nansum(upcoming, axis=0) / count.clip(min=1)
            known = (count > 0) & np.isfinite(trace.radio[end])
            serving = trace.serving[end].clip(min=0)
            index = np.arange(len(trace.ids))
            labels = dict(risk=radio[index, serving] < 40, risk_mask=known[index, serving],
                          attack=attack[end], load=trace.load[end + 10], radio=radio / 100, radio_mask=known)
            examples.append((window, {key: torch.as_tensor(value, dtype=torch.float32) for key, value in labels.items()}))
    return examples


def objective(output, target):
    error = (output['radio'] - target['radio']) * target['radio_mask']
    radio_loss = error.square().sum() / target['radio_mask'].sum().clamp_min(1)
    return multitask_loss(output, target, load_weight=8.) + 20 * radio_loss


@torch.no_grad()
def evaluate(model, loader):
    errors = np.zeros(6)
    model.eval()
    for graph, target in loader:
        predicted = model(graph)
        mask = target['radio_mask'].bool()
        errors += [(predicted['radio'][mask] - target['radio'][mask]).abs().sum().item() * 100,
                   (graph['edge'][:, -1, :, :, 0][mask] - target['radio'][mask]).abs().sum().item() * 100,
                   mask.sum().item(), (predicted['load'] - target['load']).abs().sum().item() * 100,
                   (graph['cell'][:, -1, :, 1] - target['load']).abs().sum().item() * 100,
                   target['load'].numel()]
    return dict(radio_mae_db=errors[0] / errors[2], persistence_radio_mae_db=errors[1] / errors[2],
                load_mae_pp=errors[3] / errors[5], persistence_load_mae_pp=errors[4] / errors[5])


def train(data, output, warm_start):
    seed_everything(2026)
    runs = sorted(data.glob('seed-*'))
    if [run.name for run in runs] != [f'seed-{seed}' for seed in range(2201, 2213)]:
        raise ValueError('Expected the 12 independent NITK training, validation and test runs')
    loaders = []
    for count, subset in enumerate((runs[:8], runs[8:10], runs[10:])):
        samples = [sample for run in subset for sample in load_examples(run)]
        loaders.append(DataLoader(samples, batch_size=32, shuffle=count == 0))
    model = TrustGraph(32, True, residual_load=True, forecast_radio=True)
    if warm_start.is_file():
        weights = torch.load(warm_start, map_location='cpu', weights_only=True)['state_dict']
        missing, unexpected = model.load_state_dict(weights, strict=False)
        if set(missing) != {'radio_head.weight', 'radio_head.bias'} or unexpected:
            raise ValueError('The previous TrustGraph checkpoint is incompatible')
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.002)
    output.mkdir(parents=True, exist_ok=True)
    best = float('inf')
    for epoch in range(18):
        model.train()
        for graph, target in loaders[0]:
            optimizer.zero_grad()
            objective(model(graph), target).backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
            optimizer.step()
        validation = evaluate(model, loaders[1])
        score = validation['radio_mae_db'] + validation['load_mae_pp']
        if score < best:
            best = score
            torch.save(model.state_dict(), output / 'trustgraph-campus.pt')
        print(f'Epoch {epoch + 1} | validation radio {validation["radio_mae_db"]:.2f} dB', flush=True)
    model.load_state_dict(torch.load(output / 'trustgraph-campus.pt', weights_only=True))
    metrics = evaluate(model, loaders[2])
    metrics['test_seeds'] = [2211, 2212]
    (output / 'metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    print(json.dumps(metrics), flush=True)


@torch.no_grad()
def predict(model, trace, towers):
    history = slice(-HISTORY, None)
    graph = features(trace.motion[history], trace.serving[history], trace.radio[history],
                     trace.load[history], towers)
    graph['vehicle'][0, :, 3:5] = 0
    return {key: value[0].numpy() for key, value in model({key: value[None] for key, value in graph.items()}).items()}


def choose(trace, forecast, towers, ue, current, native_candidate):
    if trace is None or forecast is None or ue not in trace.ids:
        return 'fallback_history', {}
    i = trace.ids.index(ue)
    source = current - 1
    if source < 0 or source >= trace.radio.shape[2] or trace.serving[-1, i] != source:
        return 'fallback_state', {}
    observed = trace.radio[-1, i]
    if not np.isfinite(observed[source]):
        return 'fallback_radio', {}
    future = forecast['radio'][i] * 100
    load = forecast['load']
    risk = 1 / (1 + np.exp(-np.clip(forecast['risk_logits'][i], -30, 30)))
    distrust = 1 / (1 + np.exp(-np.clip(forecast['attack_logits'][i], -30, 30)))
    gain = future - future[source]
    position = trace.motion[-1, i, :2]
    movement = position - trace.motion[-HISTORY, i, :2]
    projected_range = np.linalg.norm(position + movement * (2.5 / 0.9) - towers, axis=1)
    # Roadside radio is infrastructure telemetry. Keep guardrails measured;
    # rank safe targets using the model's future quality and utilization.
    score = gain + 4 * risk - 30 * (load - load[source])
    safe = (observed >= 36) & (load <= 0.82) & (trace.load[-1] <= 0.85)
    safe[source] = False
    evidence = dict(forecast_db=np.round(future, 3).tolist(), forecast_load=load.tolist(),
                    serving_risk=float(risk), false_position_probability=float(distrust))
    if native_candidate:
        target = native_candidate - 1
        if target >= len(safe) or not np.isfinite(observed[target]):
            return 'fallback_radio', evidence
        moving_away = projected_range[target] > 1.25 * projected_range[source] + 15 and observed[source] >= 36
        if not safe[target] or moving_away or observed[target] < observed[source] - 4 or score[target] < -2:
            return 'defer', evidence
    else:
        latest = trace.fresh[-1, i]
        previous = trace.fresh[-11, i] if len(trace.fresh) >= 11 else np.full_like(latest, np.nan)
        safe &= np.isfinite([latest, previous]).all(axis=0) & (latest >= latest[source] - 2)
        safe &= (previous >= previous[source] - 8) & (gain >= 2) & (score >= 4)
        safe &= projected_range <= 1.15 * projected_range.min() + 10
        if not safe.any():
            return 'keep', evidence
        target = int(np.argmax(np.where(safe, score, -np.inf)))
    return 'request', dict(evidence, target=target + 1, measured_db=float(observed[target]),
                           forecast_gain_db=float(gain[target]), score=float(score[target]))


def serve(bridge, checkpoint):
    seed_everything(2026)
    model = TrustGraph(32, True, residual_load=True, forecast_radio=True)
    model.load_state_dict(torch.load(checkpoint, map_location='cpu', weights_only=True))
    model.eval()
    import hashlib
    (bridge / 'checkpoint.json').write_text(json.dumps({
        'sha256': hashlib.sha256(checkpoint.read_bytes()).hexdigest(), 'model': 'TrustGraph campus'}))
    towers = np.asarray(json.loads((bridge / 'campus-meta.json').read_text())['towers'], dtype=np.float32)
    (bridge / 'ready').touch()
    last_time = None
    while not (bridge / 'stop').exists():
        for path in bridge.glob('request-*.txt'):
            serial, stamp, ue, current, candidate, *mode = path.read_text().split()
            reply = bridge / f'response-{serial}.txt'
            if reply.exists():
                continue
            now = float(stamp)
            if now != last_time:
                trace = read_trace((bridge / 'run.log').read_text(encoding='utf-8'), len(towers), now)
                forecast = predict(model, trace, towers) if trace is not None and len(trace.ticks) >= HISTORY else None
                last_time = now
            choice, evidence = choose(trace, forecast, towers, int(ue), int(current), int(candidate))
            with (bridge / 'policy.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(dict(serial=int(serial), time_s=now, ue=int(ue), serving=int(current),
                                             native_candidate=int(candidate), decision=choice,
                                             proactive=mode == ['campus'], **evidence), allow_nan=False) + '\n')
            response = f'{serial} {choice}'
            if choice == 'request' and mode == ['campus']:
                response += f' {evidence["target"]} {evidence["measured_db"]}'
            temporary = reply.with_suffix('.tmp')
            temporary.write_text(response + '\n', encoding='ascii')
            temporary.replace(reply)
        time.sleep(0.01)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('train', 'serve'))
    parser.add_argument('source', type=Path)
    parser.add_argument('checkpoint', type=Path)
    parser.add_argument('--warm-start', type=Path, default=Path('outputs/nr-congestion-mae/trustgraph.pt'))
    args = parser.parse_args()
    if args.action == 'train':
        train(args.source, args.checkpoint, args.warm_start)
    else:
        serve(args.source, args.checkpoint)


if __name__ == '__main__':
    main()
