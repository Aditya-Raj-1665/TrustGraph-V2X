import csv
import json
from pathlib import Path
import time
import numpy as np
from .controller import choose_targets
from .learning import Predictor
from .simulation import ToyNetwork


def rollout(config, seed, attack_fraction, policy='reactive', predictor=None):
    env = ToyNetwork(config, seed, attack_fraction)
    history, metrics, latency = [], [], []
    for _ in range(config.steps):
        frame, _ = env.snapshot()
        history.append(frame)
        history = history[-config.history:]
        prediction = None
        if predictor and len(history) >= config.history:
            start = time.perf_counter()
            prediction = predictor(history)
            latency.append((time.perf_counter() - start) * 1000)
        targets = choose_targets(frame, config, prediction, policy == 'load_aware')
        metrics.append(env.advance(targets, frame))
    result = {'seed': seed, 'attack_fraction': attack_fraction, 'policy': policy}
    for key in metrics[0]:
        values = [m[key] for m in metrics]
        result[key] = float(np.mean(values) if key in ['delivery_proxy', 'load_fairness'] else np.sum(values))
    result['inference_ms_mean'] = float(np.mean(latency)) if latency else 0.
    result['inference_ms_p95'] = float(np.percentile(latency, 95)) if latency else 0.
    return result


def compare(config, output, baseline, trust, seeds=(1001, 1002, 1003), rates=(0., .1, .3)):
    models = {'baseline_gnn': Predictor(baseline), 'trustgraph': Predictor(trust)}
    for predictor in models.values():
        if predictor.config.history != config.history or predictor.config.dt != config.dt:
            raise ValueError('Evaluation history/dt must match training')
    rows = []
    for rate in rates:
        for seed in seeds:
            for policy in ['reactive', 'load_aware', 'baseline_gnn', 'trustgraph']:
                rows.append(rollout(config, seed, rate, policy, models.get(policy)))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'closed_loop.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summaries = []
    for rate in rates:
        for policy in ['reactive', 'load_aware', 'baseline_gnn', 'trustgraph']:
            group = [r for r in rows if r['attack_fraction'] == rate and r['policy'] == policy]
            summary = {'attack_fraction': rate, 'policy': policy, 'runs': len(group)}
            for key in ['delivery_proxy', 'handovers', 'bad_links', 'overloaded_cell_seconds', 'load_fairness']:
                values = np.array([r[key] for r in group])
                summary[key] = {'mean': float(values.mean()), 'std': float(values.std(ddof=1)) if len(values) > 1 else 0.}
            summaries.append(summary)
    report = {'source': 'toy-radio-NOT-Simu5G', 'warning': 'Engineering smoke test; not validated 5G performance or evidence of research superiority.',
              'seeds': list(seeds), 'attack_fractions': list(rates), 'summary': summaries}
    (output / 'summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report
