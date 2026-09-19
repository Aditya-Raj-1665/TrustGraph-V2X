from dataclasses import replace
from types import SimpleNamespace
import csv
import numpy as np
from trustgraph.config import Config
from trustgraph.controller import choose_targets
from trustgraph.midsem import record_replay, sumo_replay, simple_baselines
from trustgraph.simulation import ToyNetwork, generate_dataset


class ObservableOnlyPredictor:
    def __init__(self, config):
        self.config = config
        self.model = SimpleNamespace(trust_aware=True)
        self.calls = 0

    def __call__(self, frames):
        self.calls += 1
        for frame in frames:
            assert 'actual_x' not in frame and 'attack' not in frame and 'truth' not in frame
        if len(frames) < self.config.history:
            return None
        count = len(frames[-1]['serving'])
        return {'risk': np.full(count, .9), 'load': frames[-1]['load'].copy(),
                'attack_probability': np.full(count, .7)}


def test_explanations_do_not_change_actions():
    c = Config()
    env = ToyNetwork(c, 1001)
    for _ in range(40):
        frame, _ = env.snapshot()
        prediction = {'risk': np.full(c.vehicles, .95), 'load': frame['load']}
        basic = choose_targets(frame, c, prediction)
        explained, decisions = choose_targets(frame, c, prediction, explain=True)
        np.testing.assert_array_equal(explained, basic)
        assert [d['target'] for d in decisions] == explained.tolist()
        assert len(decisions) == c.vehicles
        env.advance(basic, frame)


def test_replay_preserves_causality_and_keeps_truth_out_of_inference():
    c = replace(Config(), vehicles=6, steps=30)
    predictor = ObservableOnlyPredictor(c)
    replay = record_replay(c, predictor, 1001, .5)
    assert predictor.calls > c.steps
    assert predictor.model.trust_aware is True
    for current, following in zip(replay['frames'], replay['frames'][1:]):
        assert current['targets'] == following['observed']['serving']
        assert np.isclose(following['time'] - current['time'], c.dt)
    assert replay['frames'][14]['truth']['attack'] == [0.] * 6
    assert sum(replay['frames'][15]['truth']['attack']) == 3
    assert replay['frames'][8]['prediction'] is None
    assert replay['frames'][9]['prediction'] is not None
    assert replay['frames'][-1]['total_handovers'] == len(replay['events'])


def test_clean_and_attacked_replays_share_physical_radio_conditions():
    c = replace(Config(), vehicles=6, steps=30)
    clean = record_replay(c, ObservableOnlyPredictor(c), 1001, 0.)
    attack = record_replay(c, ObservableOnlyPredictor(c), 1001, .5)
    for a, b in zip(clean['frames'], attack['frames']):
        assert a['truth']['actual_x'] == b['truth']['actual_x']
        assert a['observed']['sinr'] == b['observed']['sinr']
    assert clean['frames'][-1]['observed']['reported_x'] != attack['frames'][-1]['observed']['reported_x']


def test_sumo_replay_uses_original_rows_without_fabricating_wireless(tmp_path):
    path = tmp_path / 'mobility.csv'
    with path.open('w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['time_s','vehicle_id','x_m','y_m','speed_mps','acceleration_mps2','heading_deg','lane_id'])
        for tick in range(1, 11):
            writer.writerow([tick / 10, 'veh_001', tick, 500, 10, 0, 90, 'WC_0'])
    replay = sumo_replay(path)
    assert replay['rows'] == 10 and replay['vehicle_count'] == 1
    assert [f['time'] for f in replay['frames']] == [.5, 1.]
    assert replay['frames'][0]['vehicles'][0]['x'] == 5
    assert 'sinr' not in replay['frames'][0]['vehicles'][0]


def test_simple_baseline_uses_same_heldout_population(tmp_path):
    c = replace(Config(), vehicles=6, steps=30)
    manifest = generate_dataset(tmp_path, c, 5)
    metrics = simple_baselines(tmp_path)
    assert metrics['link']['count'] > 0
    assert metrics['attack']['count'] >= metrics['link']['count']
    assert np.isfinite(metrics['load']['rmse'])
    assert len([r for r in manifest['runs'] if r['split'] == 'test']) == 1
