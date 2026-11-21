import numpy as np

from trustgraph.nr_campus import Trace, choose


def test_campus_policy_ranks_candidates_by_forecast_and_requires_fresh_beacons():
    radio = np.tile([46, 48, 47, 40], (11, 1, 1)).astype(float)
    trace = Trace(np.arange(10, 21), [2049], np.zeros((11, 1, 3)),
                  np.zeros((11, 1), dtype=int), radio.copy(), radio.copy(), np.zeros((11, 4)))
    forecast = {'radio': np.array([[0.44, 0.50, 0.60, 0.44]]),
                'load': np.zeros(4), 'risk_logits': [0], 'attack_logits': [0]}
    towers = np.array([[-100, 0], [100, 0], [0, 100], [0, -100]])

    choice, evidence = choose(trace, forecast, towers, 2049, 1, 0)
    assert choice == 'request' and evidence['target'] == 3

    trace.fresh[0, 0, 2] = np.nan
    choice, evidence = choose(trace, forecast, towers, 2049, 1, 0)
    assert choice == 'request' and evidence['target'] == 2

    forecast['load'][1] = 0.90
    assert choose(trace, forecast, towers, 2049, 1, 0)[0] == 'keep'
