from dataclasses import replace
import numpy as np
from trustgraph.config import Config
from trustgraph.learning import train, Predictor
from trustgraph.service import handle_request
from trustgraph.simulation import generate_dataset, ToyNetwork


def test_training_checkpoint_and_service_roundtrip(tmp_path):
    c = replace(Config(), vehicles=4, steps=25, hidden=8, epochs=1, batch_size=8)
    generate_dataset(tmp_path / 'data', c, runs=5)
    report = train(tmp_path / 'data', tmp_path / 'model')
    assert np.isfinite(report['test']['loss'])
    first = Predictor(tmp_path / 'model/model.pt')
    second = Predictor(tmp_path / 'model/model.pt')
    env = ToyNetwork(c, 17)
    frames = []
    for _ in range(c.history):
        frame, _ = env.snapshot()
        frames.append(frame)
        env.advance(frame['serving'], frame)
    a, b = first(frames), second(frames)
    for key in a:
        np.testing.assert_array_equal(a[key], b[key])
    payload = {'request_id': 'roundtrip', 'frames': [{k: v.tolist() if isinstance(v, np.ndarray) else v
                                                   for k, v in frame.items()} for frame in frames]}
    response = handle_request(payload, first)
    assert response['mode'] == 'model_with_per_vehicle_fallback'
    assert len(response['target_cells']) == c.vehicles
    np.testing.assert_allclose(response['predictions']['risk'], a['risk'])
