"""Inspect completed artifacts and record reproducible environment/results."""
import csv
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    with (ROOT / 'outputs/sumo/mobility.csv').open(newline='') as file:
        rows = list(csv.DictReader(file))
    metadata = json.loads((ROOT / 'outputs/sumo/mobility.metadata.json').read_text())
    assert len(rows) == metadata['rows']
    assert len({r['vehicle_id'] for r in rows}) == 20
    assert len({(r['time_s'], r['vehicle_id']) for r in rows}) == len(rows)
    assert metadata['completed']
    assert any(float(r['speed_mps']) == 0 for r in rows)
    assert any(float(r['speed_mps']) > 1 for r in rows)
    reports = {name: json.loads((ROOT / f'outputs/demo/{name}/metrics.json').read_text())
               for name in ['baseline', 'trustgraph']}
    with (ROOT / 'outputs/demo/evaluation/closed_loop.csv').open(newline='') as file:
        experiments = list(csv.DictReader(file))
    assert len(experiments) == 36
    subprocess.run([sys.executable, '-m', 'trustgraph', 'predict', '--checkpoint', str(ROOT / 'outputs/demo/trustgraph/model.pt'),
                    '--observations', str(ROOT / 'outputs/demo/dataset/run_00053.observed.npz'),
                    '--output', str(ROOT / 'outputs/prediction.json')], check=True, capture_output=True, text=True)
    prediction = json.loads((ROOT / 'outputs/prediction.json').read_text())
    assert len(prediction['targets']) == 20
    assert len(prediction['load']) == 3
    freeze = subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True)
    pinned = [line for line in freeze.splitlines() if not line.startswith(('#', '-e')) and 'trustgraph' not in line.lower()]
    (ROOT / 'requirements-lock.txt').write_text('# Verified Windows Python 3.12 environment; install project separately with pip install -e .\n' + '\n'.join(pinned) + '\n', encoding='utf-8')
    report = {'sumo': metadata, 'closed_loop_experiments': len(experiments), 'checkpoint_cli_inference': 'passed',
              'models': {name: value['test'] for name, value in reports.items()},
              'limitations': ['Radio/network experiments are synthetic, not Simu5G.',
                              'Small engineering dataset; no claim of research superiority.']}
    (ROOT / 'outputs/validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
