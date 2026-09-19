"""Observable-only bipartite graphs and run-separated temporal labels."""
import json
from pathlib import Path
import numpy as np
import torch
from torch.utils.data import Dataset
from .config import Config
from .simulation import CELL_X

VEHICLE_FEATURES = ['reported_x/600', 'reported_y/20', 'speed/30', 'direction',
                    'motion_residual/100', 'serving_sinr/30', 'handover_age/10']
CELL_FEATURES = ['cell_x/600', 'load']
EDGE_FEATURES = ['sinr/30', 'reported_distance/1200', 'is_serving']


def build_graphs(observed, dt):
    x, y = observed['reported_x'], observed['reported_y']
    speed, direction = observed['speed'], observed['direction']
    residual = np.zeros_like(x)
    residual[1:] = (x[1:] - x[:-1]) - speed[:-1] * direction[:-1] * dt
    serving = observed['serving']
    quality = np.take_along_axis(observed['sinr'], serving[..., None], axis=2)[..., 0]
    vehicle = np.stack([x / 600, y / 20, speed / 30, direction, residual / 100,
                        quality / 30, np.minimum(observed['since_handover'], 10) / 10], axis=-1)
    cell = np.stack([np.broadcast_to(CELL_X / 600, observed['load'].shape), observed['load']], axis=-1)
    distance = np.sqrt((x[..., None] - CELL_X) ** 2 + y[..., None] ** 2)
    attached = serving[..., None] == np.arange(len(CELL_X))
    edge = np.stack([observed['sinr'] / 30, distance / 1200, attached.astype(float)], axis=-1)
    # Synthetic receiver measures all three candidate cells; unavailable edges must be masked.
    mask = np.isfinite(observed['sinr'])
    return {'vehicle': np.nan_to_num(vehicle).astype(np.float32),
            'cell': np.nan_to_num(cell).astype(np.float32),
            'edge': np.nan_to_num(edge).astype(np.float32), 'edge_mask': mask.astype(np.float32)}


def targets_at(observed, truth, t, config):
    if t + config.horizon >= len(observed['time']):
        raise ValueError('Incomplete future horizon')
    future = slice(t + 1, t + config.horizon + 1)
    serving = observed['serving'][t]
    # Current serving-link outcome is censored if the policy changes that link.
    valid = np.all(observed['serving'][future] == serving, axis=0)
    sinr = observed['sinr'][future, np.arange(len(serving)), serving]
    bad = sinr < config.bad_sinr
    risk = np.zeros(len(serving), dtype=np.float32)
    for start in range(config.horizon - config.bad_duration + 1):
        risk = np.maximum(risk, bad[start:start + config.bad_duration].all(axis=0))
    return {'risk': risk.astype(np.float32), 'risk_mask': valid.astype(np.float32),
            'load': observed['load'][t + config.horizon].astype(np.float32),
            'attack': truth['attack'][t].astype(np.float32)}


class GraphSequences(Dataset):
    def __init__(self, path, split):
        path = Path(path)
        self.config = Config.load(path / 'config.json')
        manifest = json.loads((path / 'manifest.json').read_text())
        self.items = []
        self.run_ids = set()
        for run in manifest['runs']:
            if run['split'] != split:
                continue
            self.run_ids.add(run['id'])
            with np.load(path / (run['id'] + '.observed.npz'), allow_pickle=False) as f:
                observed = dict(f)
            with np.load(path / (run['id'] + '.truth.npz'), allow_pickle=False) as f:
                truth = dict(f)
            graph = build_graphs(observed, self.config.dt)
            for t in range(self.config.history - 1, len(observed['time']) - self.config.horizon, self.config.stride):
                seq = {k: torch.from_numpy(v[t - self.config.history + 1:t + 1].copy()) for k, v in graph.items()}
                # Inference receives only this window: no predecessor exists at its first step.
                seq['vehicle'][0, :, 4] = 0
                label = {k: torch.from_numpy(v) for k, v in targets_at(observed, truth, t, self.config).items()}
                self.items.append((seq, label))
        if not self.items:
            raise ValueError(f'No sequences in {split}')

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        return self.items[index]
