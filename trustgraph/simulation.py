"""Deterministic toy radio environment. This is NOT a Simu5G/3GPP model."""
from dataclasses import replace
import json
from pathlib import Path
import numpy as np
from .config import Config

CELL_X = np.array([-400., 0., 400.], dtype=np.float32)


class ToyNetwork:
    def __init__(self, config: Config, seed: int, attack_fraction=None):
        self.config = config
        self.seed = seed
        # Independent streams keep physical conditions identical across attack rates/policies.
        self.rng = np.random.default_rng(seed)
        self.attack_rng = np.random.default_rng(seed + 100000)
        self.x = self.rng.uniform(-580, 580, config.vehicles)
        self.speed = self.rng.uniform(10, 27, config.vehicles)
        self.direction = self.rng.choice([-1., 1.], config.vehicles)
        self.y = self.rng.choice([-8., 8.], config.vehicles)
        self.serving = np.abs(self.x[:, None] - CELL_X).argmin(1)
        self.last_handover = np.full(config.vehicles, -100.)
        self.previous_cell = np.full(config.vehicles, -1)
        self.blockage = np.zeros(3)
        rate = config.attack_fraction if attack_fraction is None else attack_fraction
        if not 0 <= rate <= 1:
            raise ValueError('attack_fraction must be in [0, 1]')
        self.attackers = np.zeros(config.vehicles, dtype=bool)
        order = self.attack_rng.permutation(config.vehicles)
        self.attackers[order[:round(rate * config.vehicles)]] = True
        self.t = 0

    def snapshot(self):
        c = self.config
        self.blockage = np.maximum(0, self.blockage - 0.25)
        events = self.rng.random(3) < 0.025
        self.blockage[events] = self.rng.uniform(6, 14, events.sum())
        distance = np.sqrt((self.x[:, None] - CELL_X) ** 2 + self.y[:, None] ** 2)
        sinr = 24 - distance / 20 - self.blockage + self.rng.normal(0, 1, distance.shape)
        count = np.bincount(self.serving, minlength=3)
        load = count / c.cell_capacity
        # False-position attack changes only the report, never physical channel calculations.
        active = self.attackers & (self.t >= 15)
        reported_x = self.x.copy()
        reported_x[active] += c.attack_offset + self.attack_rng.normal(0, 35, active.sum())
        return {
            'time': self.t * c.dt,
            'vehicle_ids': [f'veh_{i:03d}' for i in range(c.vehicles)],
            'reported_x': reported_x.astype(np.float32),
            'reported_y': self.y.astype(np.float32).copy(),
            'speed': self.speed.astype(np.float32).copy(),
            'direction': self.direction.astype(np.float32).copy(),
            'sinr': sinr.astype(np.float32),
            'serving': self.serving.copy(),
            'load': load.astype(np.float32),
            'since_handover': (self.t * c.dt - self.last_handover).astype(np.float32),
        }, {'actual_x': self.x.copy(), 'attack': active.astype(np.float32)}

    def advance(self, targets, snapshot):
        targets = np.asarray(targets, dtype=int)
        if targets.shape != self.serving.shape or np.any((targets < 0) | (targets >= 3)):
            raise ValueError('Invalid handover targets')
        changed = targets != self.serving
        pingpong = changed & (targets == self.previous_cell) & (snapshot['since_handover'] < 5)
        self.previous_cell[changed] = self.serving[changed]
        self.last_handover[changed] = self.t * self.config.dt
        self.serving = targets.copy()
        chosen_sinr = snapshot['sinr'][np.arange(len(targets)), targets]
        load = np.bincount(targets, minlength=3) / self.config.cell_capacity
        delivery = np.clip((chosen_sinr + 5) / 20, 0, 1) / np.maximum(1, load[targets])
        # A small explicit switching penalty for the toy environment only.
        delivery = np.clip(delivery - changed * 0.08, 0, 1)
        stats = {
            'handovers': int(changed.sum()), 'pingpong': int(pingpong.sum()),
            'bad_links': int((chosen_sinr < self.config.bad_sinr).sum()),
            'delivery_proxy': float(delivery.mean()),
            'overloaded_cell_seconds': float((load > 1).sum() * self.config.dt),
            'load_fairness': float(load.sum() ** 2 / (3 * np.square(load).sum() + 1e-9)),
        }
        self.x += self.speed * self.direction * self.config.dt
        bounced = np.abs(self.x) > 600
        self.direction[bounced] *= -1
        self.x = np.clip(self.x, -600, 600)
        self.t += 1
        return stats


def generate_run(config, seed):
    from .controller import choose_targets
    env = ToyNetwork(config, seed)
    frames, truth = [], []
    for _ in range(config.steps):
        frame, label = env.snapshot()
        frames.append(frame)
        truth.append(label)
        env.advance(choose_targets(frame, config), frame)
    observed = {k: np.stack([f[k] for f in frames]) for k in frames[0] if k != 'vehicle_ids'}
    observed['vehicle_ids'] = np.asarray(frames[0]['vehicle_ids'])
    ground_truth = {k: np.stack([f[k] for f in truth]) for k in truth[0]}
    return observed, ground_truth


def generate_dataset(path, config, runs=12):
    if runs < 5:
        raise ValueError('At least five independent runs are required for train/validation/test')
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if (path / 'manifest.json').exists():
        raise FileExistsError(f'Dataset exists: {path}; choose a new output directory')
    n_train = max(1, int(runs * .6))
    n_val = max(1, int(runs * .2))
    manifest = {'source': 'toy-radio-NOT-Simu5G', 'runs': [], 'schema_version': 1}
    for i in range(runs):
        seed = config.seed + i
        run = f'run_{seed:05d}'
        # Include clean training runs, keeping run families in a single partition.
        rate = 0.0 if i % 4 == 0 else config.attack_fraction
        observed, truth = generate_run(replace(config, attack_fraction=rate), seed)
        np.savez_compressed(path / f'{run}.observed.npz', **observed)
        np.savez_compressed(path / f'{run}.truth.npz', **truth)
        split = 'train' if i < n_train else ('validation' if i < n_train + n_val else 'test')
        manifest['runs'].append({'id': run, 'seed': seed, 'split': split, 'attack_fraction': rate})
    config.save(path / 'config.json')
    (path / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest
