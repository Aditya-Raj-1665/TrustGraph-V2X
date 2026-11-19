import json

import pytest
import torch

from trustgraph.nr_policy import decision


@pytest.mark.parametrize('previous_target, measured_target_load, predicted_target_load, expected', [
    (42, 0.55, 0.55, 'request'),
    (None, 0.55, 0.55, 'keep_radio'),
    (39, 0.55, 0.55, 'keep_radio'),
    (42, 0.61, 0.55, 'keep_load'),
    (42, 0.55, 0.61, 'keep_forecast'),
])
def test_early_offload_checks_two_beacons_and_cell_capacity(
    tmp_path, previous_target, measured_target_load, predicted_target_load, expected,
):
    class Model:
        input_load_scale = 1.

        def __call__(self, graph):
            return {'risk_logits': torch.zeros(1, 1), 'attack_logits': torch.zeros(1, 1),
                    'load': torch.tensor([[0.95, predicted_target_load]])}

    log = [f'TRUSTGRAPH_OBS {tick} 2049 400 3 12 1 0.95 {measured_target_load}' for tick in range(11, 21)]
    log.extend(['UE 2049 broadcast frame from 1 with RSSI: 44 at 1',
                'UE 2049 broadcast frame from 1 with RSSI: 44 at 2',
                'UE 2049 broadcast frame from 2 with RSSI: 42 at 2'])
    if previous_target is not None:
        log.append(f'UE 2049 broadcast frame from 2 with RSSI: {previous_target} at 1')
    (tmp_path / 'run.log').write_text('\n'.join(log), encoding='utf-8')
    (tmp_path / 'trial.json').write_text(json.dumps({'seed': 1151}), encoding='utf-8')

    choice, evidence = decision(Model(), tmp_path, 2.000021, 2049, 1, 2, early=True)
    assert choice == expected
    if choice == 'request':
        assert evidence['candidate_rssi_db'] == 42
