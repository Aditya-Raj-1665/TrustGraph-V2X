from dataclasses import replace
import numpy as np
import pytest
import torch
from trustgraph.config import Config
from trustgraph.controller import choose_targets
from trustgraph.graphs import build_graphs, targets_at, GraphSequences
from trustgraph.learning import binary_metrics
from trustgraph.model import TrustGraph, multitask_loss
from trustgraph.simulation import generate_run, generate_dataset, ToyNetwork


def config(**kwargs):
    return replace(Config(), vehicles=6, steps=35, epochs=1, hidden=8, **kwargs)


def test_reproducible_and_attack_does_not_change_physics():
    c = config()
    clean, _ = generate_run(replace(c, attack_fraction=0), 12)
    attacked, truth = generate_run(replace(c, attack_fraction=.5), 12)
    repeated, _ = generate_run(replace(c, attack_fraction=.5), 12)
    np.testing.assert_array_equal(clean['sinr'], attacked['sinr'])
    np.testing.assert_array_equal(clean['load'], attacked['load'])
    np.testing.assert_array_equal(attacked['reported_x'], repeated['reported_x'])
    assert np.any(clean['reported_x'] != attacked['reported_x'])
    assert truth['attack'][0].sum() == 0
    assert truth['attack'][-1].sum() == 3


def test_graphs_ignore_truth_and_future():
    c = config()
    observed, truth = generate_run(c, 42)
    graph = build_graphs(observed, c.dt)
    changed = {k: v.copy() for k, v in observed.items()}
    changed['actual_x'] = truth['actual_x'] * 100
    changed['attack'] = truth['attack']
    changed['reported_x'][20:] += 10000
    altered = build_graphs(changed, c.dt)
    for key in graph:
        np.testing.assert_array_equal(graph[key][:20], altered[key][:20])


def test_label_duration_horizon_and_handover_censoring():
    c = config()
    observed, truth = generate_run(c, 42)
    observed['serving'][:] = 0
    observed['sinr'][:] = 30
    observed['sinr'][11:14, 0, 0] = -10
    observed['sinr'][11:13, 1, 0] = -10
    observed['serving'][12, 2] = 1
    target = targets_at(observed, truth, 10, c)
    assert target['risk'][0] == 1
    assert target['risk'][1] == 0
    assert target['risk_mask'][2] == 0
    np.testing.assert_array_equal(target['load'], observed['load'][20])
    with pytest.raises(ValueError, match='Incomplete'):
        targets_at(observed, truth, 30, c)


def test_splits_are_run_disjoint(tmp_path):
    generate_dataset(tmp_path, config(), runs=5)
    datasets = [GraphSequences(tmp_path, split) for split in ['train', 'validation', 'test']]
    assert len(set.union(*(d.run_ids for d in datasets))) == 5
    assert not datasets[0].run_ids & datasets[1].run_ids
    assert not datasets[0].run_ids & datasets[2].run_ids
    assert all(torch.all(graph['vehicle'][0, :, 4] == 0) for graph, _ in datasets[0])
    with pytest.raises(FileExistsError):
        generate_dataset(tmp_path, config(), runs=5)


def test_model_gradients_and_vehicle_permutation():
    torch.manual_seed(42)
    c = config()
    observed, truth = generate_run(c, 42)
    graph = {k: torch.from_numpy(v[:c.history]).unsqueeze(0) for k, v in build_graphs(observed, c.dt).items()}
    model = TrustGraph(8, True)
    result = model(graph)
    target = {k: torch.from_numpy(v).unsqueeze(0) for k, v in targets_at(observed, truth, 9, c).items()}
    multitask_loss(result, target).backward()
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())
    permutation = torch.tensor([3, 0, 2, 1, 5, 4])
    permuted = {k: v[:, :, permutation] if k != 'cell' else v for k, v in graph.items()}
    after = model(permuted)
    torch.testing.assert_close(after['risk_logits'], result['risk_logits'][:, permutation], atol=1e-6, rtol=1e-5)
    torch.testing.assert_close(after['load'], result['load'], atol=1e-6, rtol=1e-5)


def test_trust_gate_affects_link_and_load_heads():
    c = config()
    observed, _ = generate_run(c, 42)
    graph = {k: torch.from_numpy(v[:c.history]).unsqueeze(0) for k, v in build_graphs(observed, c.dt).items()}
    model = TrustGraph(8, True)
    with torch.no_grad():
        model.attack_head.weight.zero_()
        model.attack_head.bias.fill_(-20)
        trusted = model(graph)
        model.attack_head.bias.fill_(20)
        untrusted = model(graph)
    assert not torch.allclose(trusted['load'], untrusted['load'])
    assert not torch.allclose(trusted['risk_logits'], untrusted['risk_logits'])


def test_controller_fallback_dwell_and_capacity():
    c = config()
    frame, _ = ToyNetwork(c, 42).snapshot()
    frame['serving'][:] = 0
    frame['sinr'][:] = [10, 20, 5]
    frame['load'][:] = [6 / 9, 0, 0]
    frame['since_handover'][:] = 10
    reactive = choose_targets(frame, c)
    prediction = {'risk': np.full(6, .5), 'load': np.array([1., 0., 0.])}
    np.testing.assert_array_equal(choose_targets(frame, c, prediction), reactive)
    prediction['risk'][:] = np.nan
    np.testing.assert_array_equal(choose_targets(frame, c, prediction), reactive)
    frame['since_handover'][:] = 0
    np.testing.assert_array_equal(choose_targets(frame, c), frame['serving'])
    frame['since_handover'][:] = 10
    c = replace(c, cell_capacity=2)
    target = choose_targets(frame, c)
    assert (target == 1).sum() <= 2


def test_auc_ties_and_single_class():
    assert binary_metrics([0, 1], [.5, .5])['auroc'] == .5
    assert binary_metrics([0, 1], [.1, .9])['auroc'] == 1.
    assert binary_metrics([0, 0], [.1, .2])['auroc'] is None


def test_invalid_config():
    with pytest.raises(ValueError):
        config(attack_fraction=1.5)
