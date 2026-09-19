"""Build an offline presentation package from measured project outputs.

All replay predictions are real checkpoint outputs. Ground truth is stored
only in replay overlays and never enters Predictor or the controller.
"""
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
import torch
from .config import Config
from .controller import choose_targets
from .graphs import GraphSequences
from .learning import Predictor, binary_metrics
from .simulation import CELL_X, ToyNetwork


def plain(value):
    if isinstance(value, np.ndarray):
        return np.round(value, 5).tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def simple_baselines(dataset):
    samples = GraphSequences(dataset, 'test')
    ys, risks, attacks, ps, aps, errors = [], [], [], [], [], []
    for graph, target in samples:
        valid = target['risk_mask'].bool()
        sinr = graph['vehicle'][-1, :, 5].numpy() * 30
        # Fixed rules, specified before inspecting held-out outcomes.
        risk = 1 / (1 + np.exp(np.clip((sinr - samples.config.bad_sinr) / 3, -60, 60)))
        anomaly = np.clip(np.abs(graph['vehicle'][-1, :, 4].numpy()) * 100 / 50, 0, 1)
        ys.extend(target['risk'][valid].tolist())
        ps.extend(risk[valid.numpy()].tolist())
        attacks.extend(target['attack'].tolist())
        aps.extend(anomaly.tolist())
        errors.extend((graph['cell'][-1, :, 1] - target['load']).tolist())
    error = np.asarray(errors)
    return {'name': 'Fixed persistence and motion rules',
            'link': binary_metrics(ys, ps), 'attack': binary_metrics(attacks, aps),
            'load': {'mae': float(np.abs(error).mean()), 'rmse': float(np.sqrt((error ** 2).mean()))},
            'definitions': {'link': 'sigmoid((8 - current serving SINR) / 3), threshold 0.5',
                            'load': 'Current load persists one second into the future',
                            'attack': 'abs(position step - expected motion) / 50, clipped to [0,1]; threshold 0.5'}}


def record_replay(config, predictor, seed, fraction):
    env = ToyNetwork(config, seed, fraction)
    history, frames, events = [], [], []
    total_handovers = 0
    for step in range(config.steps):
        observed, truth = env.snapshot()
        history.append(observed)
        history = history[-config.history:]
        prediction = predictor(history)
        without_gate = None
        if prediction is not None:
            # Same model and observations, only the gate is disabled for this diagnostic.
            original = predictor.model.trust_aware
            try:
                predictor.model.trust_aware = False
                without_gate = predictor(history)
            finally:
                predictor.model.trust_aware = original
        targets, decisions = choose_targets(observed, config, prediction, explain=True)
        changed = np.flatnonzero(targets != observed['serving'])
        for index in changed:
            events.append({'step': step, 'time': round(observed['time'], 2), 'vehicle': int(index),
                           'from': int(observed['serving'][index]), 'to': int(targets[index]),
                           'reason': decisions[index]['reason'], 'mode': decisions[index]['mode']})
        stats = env.advance(targets, observed)
        total_handovers += len(changed)
        frames.append({'time': round(observed['time'], 2), 'observed': {k: plain(v) for k, v in observed.items() if k != 'vehicle_ids'},
                       'truth': {k: plain(v) for k, v in truth.items()},
                       'prediction': {k: plain(v) for k, v in prediction.items()} if prediction is not None else None,
                       'gate_disabled': {k: plain(v) for k, v in without_gate.items()} if without_gate is not None else None,
                       'targets': targets.tolist(), 'decisions': decisions,
                       'stats': stats, 'total_handovers': total_handovers})
    return {'seed': seed, 'attack_fraction': fraction, 'source': 'Synthetic radio and mobility',
            'vehicle_ids': observed['vehicle_ids'], 'cell_x': CELL_X.tolist(),
            'attack_start_s': 15 * config.dt if fraction else None, 'frames': frames, 'events': events}


def sumo_replay(csv_path):
    frames = {}
    ids = set()
    count = 0
    with Path(csv_path).open(newline='', encoding='utf-8') as file:
        for row in csv.DictReader(file):
            count += 1
            ids.add(row['vehicle_id'])
            tick = round(float(row['time_s']) * 10)
            if tick % 5:
                continue  # Half-second playback frames from the 100 ms source export.
            frames.setdefault(tick, []).append({'id': row['vehicle_id'], 'x': float(row['x_m']),
                                                'y': float(row['y_m']), 'speed': float(row['speed_mps']),
                                                'heading': float(row['heading_deg']), 'lane': row['lane_id']})
    if not frames:
        raise ValueError('SUMO export contains no replayable telemetry')
    return {'source': 'Recorded SUMO TraCI mobility; no RF or traffic-light-state telemetry',
            'rows': count, 'vehicle_count': len(ids),
            'frames': [{'time': tick / 10, 'vehicles': vehicles} for tick, vehicles in sorted(frames.items())]}


def build_package(project, output, seed=1001):
    project, output = Path(project).resolve(), Path(output).resolve()
    demo = project / 'outputs/demo'
    config = Config.load(demo / 'dataset/config.json')
    checkpoint = demo / 'trustgraph/model.pt'
    predictor = Predictor(checkpoint)
    output.mkdir(parents=True, exist_ok=True)
    metrics = {name: json.loads((demo / name / 'metrics.json').read_text()) for name in ['baseline', 'trustgraph']}
    payload = {'schema_version': 1, 'built_utc': datetime.now(timezone.utc).isoformat(),
               'config': asdict(config), 'metrics': metrics,
               'simple_baseline': simple_baselines(demo / 'dataset'),
               'network_results': json.loads((demo / 'evaluation/summary.json').read_text()),
               'sumo': sumo_replay(project / 'outputs/sumo/mobility.csv'),
               'replays': {}, 'provenance': {'checkpoint_sha256': fingerprint(checkpoint),
                   'sumo_csv_sha256': fingerprint(project / 'outputs/sumo/mobility.csv'),
                   'demo_seed': seed, 'seed_selection': 'Fixed first evaluation seed, not selected by prediction quality',
                   'gate_comparison': 'Same learned weights with sender trust gating disabled at inference',
                   'model_checkpoint': 'outputs/demo/trustgraph/model.pt'}}
    for name, fraction in [('clean', 0.), ('attack', .2)]:
        print(f'Recording {name} replay with seed {seed}', flush=True)
        payload['replays'][name] = record_replay(config, predictor, seed, fraction)
    # Assessment values are computed from source arrays, never written as invented demo scores.
    data = json.dumps(payload, separators=(',', ':'), allow_nan=False).replace('</', '<\\/')
    (output / 'data.js').write_text('window.TRUSTGRAPH_DATA=' + data + ';\n', encoding='utf-8')
    (output / 'evidence.json').write_text(json.dumps({k: v for k, v in payload.items() if k not in ['replays', 'sumo']}, indent=2), encoding='utf-8')
    assets = Path(__file__).parent / 'web'
    for name in ['index.html', 'app.js', 'style.css', 'slides.html', 'report.html', 'presentation.js']:
        shutil.copyfile(assets / name, output / name)
    (output / 'OPEN_DEMO.cmd').write_text('@echo off\nstart "" "%~dp0index.html"\n', encoding='utf-8')
    shutil.copyfile(project / 'docs/MIDSEM_DEMO_GUIDE.md', output / 'DEMO_GUIDE.md')
    return {'output': str(output), 'network_frames': {k: len(v['frames']) for k, v in payload['replays'].items()},
            'sumo_frames': len(payload['sumo']['frames']), 'checkpoint_sha256': payload['provenance']['checkpoint_sha256']}
