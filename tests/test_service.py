import numpy as np
import pytest
from trustgraph.config import Config
from trustgraph.service import handle_request, validate_frames
from trustgraph.simulation import ToyNetwork


def request():
    frame, _ = ToyNetwork(Config(), 42).snapshot()
    return {'request_id': 'test', 'frames': [{k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in frame.items()}]}


def test_warmup_returns_reactive_action():
    class Warmup:
        config = Config()

        def __call__(self, frames):
            return None

    result = handle_request(request(), Warmup())
    assert result['mode'] == 'reactive_warmup'
    assert len(result['target_cells']) == 20
    assert result['request_id'] == 'test'


def test_rejects_nonfinite_radio_and_out_of_order_time():
    payload = request()
    payload['frames'][0]['sinr'][0][0] = float('nan')
    with pytest.raises(ValueError, match='finite'):
        validate_frames(payload['frames'], Config())
    payload = request()
    payload['frames'].append(payload['frames'][0].copy())
    with pytest.raises(ValueError, match='ordered'):
        validate_frames(payload['frames'], Config())


def test_rejects_identity_changes():
    payload = request()
    next_frame = payload['frames'][0].copy()
    next_frame['time'] = .1
    next_frame['vehicle_ids'] = list(reversed(next_frame['vehicle_ids']))
    payload['frames'].append(next_frame)
    with pytest.raises(ValueError, match='identity'):
        validate_frames(payload['frames'], Config())
