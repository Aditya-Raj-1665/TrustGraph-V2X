"""Local worker for live decisions in the Simu5G handover experiment."""
import argparse
import json
from pathlib import Path
import re
import time

import numpy as np
import torch

from .learning import seed_everything
from .model import TrustGraph
from .nr_trials import BEACON, HISTORY, LOAD_SCALE, graph_features


OBSERVATION = re.compile(
    r'TRUSTGRAPH_OBS (\d+) (\d+) (\S+) (\S+) (\S+) (\d+) (\S+) (\S+)')


def observation_window(log, now):
    observations = {}
    for tick, ue, x, y, speed, cell, dl1, dl2 in OBSERVATION.findall(log):
        tick = int(tick)
        if tick / 10 <= now:
            observations.setdefault(tick, {})[int(ue)] = (float(x), float(y), float(speed),
                                                         int(cell), float(dl1), float(dl2))
    ticks = sorted(observations)[-HISTORY:]
    if len(ticks) < HISTORY or ticks[-1] - ticks[0] != HISTORY - 1:
        return None
    ids = sorted(observations[ticks[-1]])
    if any(sorted(observations[tick]) != ids for tick in ticks):
        return None
    rows = np.asarray([[observations[tick][ue] for ue in ids] for tick in ticks], dtype=np.float32)
    radio = np.full((HISTORY, len(ids), 2), np.nan, dtype=np.float32)
    for ue, cell, db, timestamp in BEACON.findall(log):
        if int(ue) in ids and float(timestamp) <= now:
            radio[np.asarray(ticks) / 10 >= float(timestamp), ids.index(int(ue)), int(cell) - 1] = float(db)
    return ticks, ids, rows[..., :3].copy(), rows[..., 3].astype(int) - 1, radio, rows[:, 0, 4:]


@torch.no_grad()
def decision(model, run, now, ue, current, candidate, early=False):
    log = (run / 'run.log').read_text(encoding='utf-8')
    window = observation_window(log, now)
    if window is None:
        return 'fallback_history', {}
    ticks, ids, positions, serving, radio, load = window
    if ue not in ids:
        return 'fallback_state', {}
    index = ids.index(ue)
    current -= 1
    candidate -= 1
    if min(current, candidate) < 0 or max(current, candidate) > 1 or serving[-1, index] != current:
        return 'fallback_state', {}
    if not np.isfinite(radio[-1, index]).all():
        return 'fallback_radio', {}
    if early:
        beacon_time = now // 1
        measurements = {(int(cell) - 1, float(t)): float(db) for node, cell, db, t in BEACON.findall(log)
                        if int(node) == ue and float(t) in (beacon_time, beacon_time - 1)}
        for timestamp in (beacon_time, beacon_time - 1):
            source_db = measurements.get((current, timestamp), float('nan'))
            target_db = measurements.get((candidate, timestamp), float('nan'))
            if not (np.isfinite([source_db, target_db]).all() and target_db >= 40 and target_db >= source_db - 3):
                return 'keep_radio', {}
        if not (load[-1, current] > 0.8 and load[-1, candidate] <= 0.6):
            return 'keep_load', {}
    meta = json.loads((run / 'trial.json').read_text())
    if 'false_position' in run.name:
        rng = np.random.default_rng(meta['seed'] + 811)
        for car in rng.choice(len(ids), size=max(1, len(ids) // 2), replace=False):
            bias = rng.choice([-1, 1]) * rng.uniform(80, 160)
            active = (np.asarray(ticks) >= 80) & (np.asarray(ticks) <= 300)
            positions[active, car, 0] += bias + 4 * np.sin(np.asarray(ticks)[active] / 3)
    current_db, target_db = map(float, radio[-1, index, [current, candidate]])
    advantage = target_db - current_db
    if model is None:
        risk = float(current_db < 40)
        future_load = load[-1]
        attack_score = 0.0
    else:
        features = graph_features(positions, serving, radio, load, model.input_load_scale)
        features['vehicle'][0, :, 3:5] = 0
        prediction = model({key: torch.from_numpy(value)[None] for key, value in features.items()})
        risk = float(torch.sigmoid(prediction['risk_logits'])[0, index])
        future_load = prediction['load'][0].numpy() * model.input_load_scale
        attack_score = float(torch.sigmoid(prediction['attack_logits'])[0, index])
    # Act only on a measured candidate. Low-risk small improvements can be
    # deferred if the target is busier. Mark stale/invalid data as fallback.
    score = advantage + 10 * risk - 100 * float(future_load[candidate] - future_load[current])
    if early:
        choice = 'request' if future_load[current] > 0.8 and future_load[candidate] <= 0.6 else 'keep_forecast'
    else:
        choice = 'request' if score >= 4 and advantage >= 0 else 'defer'
    return choice, dict(risk=risk, predicted_load=future_load.tolist(), candidate_advantage_db=advantage,
                        candidate_rssi_db=target_db, attack_score=attack_score, score=score)


def serve(root, checkpoints):
    seed_everything(2026)
    models = {'fixed_rules': None}
    for name in ('trustgraph', 'graph_without_trust'):
        checkpoint = torch.load(checkpoints / f'{name}.pt', map_location='cpu', weights_only=True)
        model = TrustGraph(checkpoint['hidden'], checkpoint['trust_aware'],
                           residual_load=checkpoint.get('residual_load', False))
        model.input_load_scale = checkpoint.get('load_scale', LOAD_SCALE)
        model.load_blend = checkpoint.get('load_blend', 1.)
        model.load_state_dict(checkpoint['state_dict'])
        models[name] = model.eval()
    processed = set()
    print('Local Simu5G policy worker ready', flush=True)
    while True:
        for request in root.glob('suite.*/trial-*/request-*.txt'):
            run = request.parent
            if request in processed or (run / 'finished').exists():
                continue
            serial, timestamp, ue, current, candidate, *kind = request.read_text().split()
            reply = run / f'response-{serial}.txt'
            if reply.exists():
                processed.add(request)
                continue
            name = run.name.rsplit('-', 1)[1].removesuffix('_early')
            early = kind == ['early']
            now = float(timestamp)
            choice, evidence = decision(models[name], run, now, int(ue), int(current), int(candidate), early)
            with (run / 'policy.jsonl').open('a', encoding='utf-8') as out:
                out.write(json.dumps(dict(time_s=now, ue=int(ue), serving=int(current),
                                          candidate=int(candidate), decision=choice, early=early, **evidence)) + '\n')
            response = run / f'response-{serial}.tmp'
            measurement = f' {evidence["candidate_rssi_db"]}' if early and choice == 'request' else ''
            response.write_text(f'{serial} {choice}{measurement}\n', encoding='ascii')
            response.replace(reply)
            processed.add(request)
        time.sleep(0.015)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('checkpoints', type=Path)
    args = parser.parse_args()
    serve(args.root, args.checkpoints)
