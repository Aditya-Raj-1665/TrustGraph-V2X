from dataclasses import asdict, dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Config:
    vehicles: int = 20
    steps: int = 180
    dt: float = 0.1
    history: int = 10
    horizon: int = 10
    bad_duration: int = 3
    bad_sinr: float = 8.0
    cell_capacity: float = 9.0
    attack_fraction: float = 0.2
    attack_offset: float = 250.0
    seed: int = 42
    hidden: int = 32
    epochs: int = 8
    batch_size: int = 32
    learning_rate: float = 0.002
    stride: int = 5
    handover_margin: float = 3.0
    dwell_seconds: float = 1.0
    risk_threshold: float = 0.5
    confidence_threshold: float = 0.6

    def __post_init__(self):
        if min(self.vehicles, self.steps, self.history, self.horizon,
               self.bad_duration, self.hidden, self.epochs, self.batch_size, self.stride) < 1:
            raise ValueError('Counts must be positive')
        if self.steps < self.history + self.horizon:
            raise ValueError('steps must cover history plus prediction horizon')
        if self.bad_duration > self.horizon:
            raise ValueError('bad_duration must not exceed horizon')
        if self.dt <= 0 or self.cell_capacity <= 0 or self.learning_rate <= 0:
            raise ValueError('dt, capacity and learning rate must be positive')
        if not 0 <= self.attack_fraction <= 1:
            raise ValueError('attack_fraction must be in [0, 1]')
        if not 0 <= self.confidence_threshold <= 1 or not 0 <= self.risk_threshold <= 1:
            raise ValueError('Probability thresholds must be in [0, 1]')

    @classmethod
    def load(cls, path=None):
        return cls(**json.loads(Path(path).read_text())) if path else cls()

    def save(self, path):
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding='utf-8')
