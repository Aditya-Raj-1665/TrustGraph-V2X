"""Check actual completed serving-cell changes in an OMNeT++ text vector."""
import argparse
import json
from pathlib import Path
import shlex


def vector_samples(path, module_suffix, statistic, node='ue[0]'):
    columns = {}
    samples = []
    for line in Path(path).read_text().splitlines():
        if line.startswith('vector '):
            fields = shlex.split(line)
            if f'.{node}.' in fields[2] and fields[2].endswith(module_suffix) and fields[3] == statistic:
                columns[fields[1]] = fields[4]
        elif line and line[0].isdigit():
            fields = line.split()
            if fields[0] in columns:
                values = dict(zip(columns[fields[0]], fields[1:]))
                samples.append((float(values['T']), float(values['V'])))
    return sorted(samples)


def serving_cells(path, node='ue[0]'):
    return [(time, int(cell)) for time, cell in
            vector_samples(path, '.nrConnectionControl', 'servingCell:vector', node)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--stationary', action='store_true')
    parser.add_argument('--node', default='ue[0]')
    args = parser.parse_args()
    samples = serving_cells(args.directory / 'handover.vec', args.node)
    positive = [(time, cell) for time, cell in samples if cell > 0]
    changes = [(time, previous, current) for (_, previous), (time, current)
               in zip(positive, positive[1:]) if previous != current]
    log = (args.directory / 'run.log').read_text(errors='replace')
    assert 'Simulation time limit reached' in log, 'Run did not reach the time limit'
    assert positive, 'No serving-cell statistics found'
    packets = vector_samples(args.directory / 'handover.vec', '.app[0]', 'cbrRcvdPkt:vector', args.node)
    assert packets, 'No received application packets found'
    if args.stationary:
        assert not changes, 'Stationary control changed cells unexpectedly'
    else:
        assert changes, 'No completed serving-cell change found'
        assert any(old == 1 and new == 2 for _, old, new in changes), 'Expected gNB 1 to gNB 2 transition missing'
        change_time = next(time for time, old, new in changes if old == 1 and new == 2)
        assert any(time < change_time for time, _ in packets), 'No traffic received before handover'
        assert any(time > change_time for time, _ in packets), 'No traffic received after handover'
    report = {'passed': True, 'stationary': args.stationary,
              'serving_cell_samples': samples, 'completed_changes': changes,
              'received_packets': len(packets), 'last_received_packet_time_s': packets[-1][0],
              'node': args.node, 'scope': 'Conventional Simu5G NR handover'}
    (args.directory / 'verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
