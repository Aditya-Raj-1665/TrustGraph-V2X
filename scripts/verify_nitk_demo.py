"""Check each campus vehicle's visible handover against Simu5G and SUMO."""

import csv
from collections import defaultdict
import json
from math import dist
from pathlib import Path
import re
import statistics
import sys
import xml.etree.ElementTree as ET

from prepare_nitk_demo import END_TIME


def read_vectors(path):
    """Read the radio, display, motion and packet statistics in one pass."""
    wanted = {'servingCell:vector', 'displayedServingCell', 'displayedTrustGraphHandover',
              'cbrRcvdPkt:vector', 'cbrFrameDelay:vector', 'sumoX', 'sumoY', 'avgServedBlocksDl:vector'}
    names = {}
    samples = defaultdict(list)
    with path.open() as stream:
        for line in stream:
            if line.startswith('vector '):
                _, serial, module, name, columns = line.split()
                if name not in wanted:
                    continue
                if name == 'servingCell:vector' and not module.endswith('.nrConnectionControl'):
                    continue
                node = module.split('.')[1]
                if not node.startswith(('car[', 'gnb')):
                    continue
                names[serial] = ((node, name), columns.index('T'), columns.index('V'))
            elif line and line[0].isdigit():
                serial, _, rest = line.partition('\t')
                if serial in names:
                    key, time_column, value_column = names[serial]
                    fields = rest.split()
                    samples[key].append((float(fields[time_column]), float(fields[value_column])))
    return samples


def verify(directory):
    log = (directory / 'run.log').read_text(encoding='utf-8')
    expected = json.loads((directory / 'demo-expected.json').read_text())
    mapping = dict(re.findall(r'TRUSTGRAPH_VEHICLE (car\[\d+\]) (\S+)', log))
    if set(mapping.values()) != expected.keys() or len(mapping) != len(expected):
        raise ValueError(f'SUMO and Simu5G vehicle lists differ: {mapping}')
    if f'Simulation time limit reached -- at t={END_TIME}s' not in log:
        raise ValueError('The campus simulation did not reach its configured end')

    bounds = ET.parse(directory / 'road.net.xml').find('location').attrib['convBoundary']
    min_x, _, _, max_y = map(float, bounds.split(','))
    positions = {vehicle: {} for vehicle in expected}
    for step in ET.parse(directory / 'sumo-fcd.xml').iter('timestep'):
        tick = round(float(step.attrib['time']) * 10) + 1
        for car in step.findall('vehicle'):
            positions[car.attrib['id']][tick] = (
                float(car.attrib['x']) - min_x + 25, max_y - float(car.attrib['y']) + 25)

    samples = read_vectors(directory / 'handover.vec')
    scalar = (directory / 'handover.sca').read_text()
    rates = re.findall(r'^scalar TrustGraphRoad\.server\.app\[\d+\] cbrGeneratedThroughput:simu5g_rateavg (\S+)$',
                       scalar, re.MULTILINE)
    if len(rates) != len(mapping):
        raise ValueError('Missing downlink sender statistics')
    sent = sum(round(float(rate) * END_TIME / 100) for rate in rates)
    received = 0
    delays = []
    reversals = 0
    policy_log = directory / 'policy.jsonl'
    policy = policy_log.exists()
    if policy:
        records = [json.loads(line) for line in policy_log.read_text().splitlines()]
        completed = {(float(stamp), int(ue), int(target)) for stamp, ue, target in re.findall(
            r'TRUSTGRAPH_REQUEST_COMPLETED (\S+) (\d+) (\d+)', log)}
        ue_ids = {node: int(ue) for node, ue in re.findall(
            r'^par TrustGraphRoad\.(car\[\d+\])\.cellularNic\.rrc\.nrConnectionControl macNodeId (\d+)$',
            scalar, re.MULTILINE)}
        if set(ue_ids) != set(mapping):
            raise ValueError('Missing NR vehicle identity for the policy audit')
    events = []
    for node, vehicle in sorted(mapping.items()):
        association = [(time, int(cell)) for time, cell in samples[node, 'servingCell:vector']]
        displayed = samples[node, 'displayedServingCell']
        if (not association or not displayed or association[0][1] != displayed[0][1]
                or not 0 <= displayed[0][0] - association[0][0] <= 0.100001
                or displayed[1:] != association[1:]):
            raise ValueError(f'SUMO display does not match Simu5G for {vehicle}')
        packets = samples[node, 'cbrRcvdPkt:vector']
        received += len({packet for _, packet in packets})
        delays.extend(delay * 1000 for _, delay in samples[node, 'cbrFrameDelay:vector'])
        switches = [(time, old, new) for (_, old), (time, new) in zip(association, association[1:])]
        reversals += sum(old == new and next_time - time <= 2
                         for (time, old, _), (next_time, _, new) in zip(switches, switches[1:]))
        actual = [cell for _, cell in association]
        design = expected[vehicle]
        milestones = design['cells'] if isinstance(design, dict) else design
        visits = iter(actual)
        if (actual[0] != milestones[0] or actual[-1] != milestones[-1]
                or not all(cell in visits for cell in milestones)):
            raise ValueError(f'{vehicle} expected to visit {milestones} in order, got {actual}')
        if policy:
            sources = dict(samples[node, 'displayedTrustGraphHandover'])
            if sources.keys() != {time for time, _, _ in switches}:
                raise ValueError(f'Missing display attribution for {vehicle}')
        for time, old, new in switches:
            if not packets or not packets[0][0] < time < packets[-1][0]:
                raise ValueError(f'{vehicle} did not receive packets before and after {time} s')
            event = dict(vehicle=vehicle, route=design['route'] if isinstance(design, dict) else '',
                         network_node=node, time_s=time, from_gnb=old, to_gnb=new)
            if policy:
                ue = ue_ids[node]
                is_model = (time, ue, new) in completed
                if bool(sources[time]) != is_model:
                    raise ValueError(f'Incorrect SUMO handover attribution for {vehicle} at {time} s')
                request = next((row for row in reversed(records) if row['decision'] == 'request'
                                and row['ue'] == ue and row['serving'] == old and row['target'] == new
                                and 0 < time - row['time_s'] <= 0.1), None) if is_model else None
                if is_model and request is None:
                    raise ValueError(f'No matching model inference for {vehicle} at {time} s')
                event.update(controller='trustgraph' if is_model else 'native_fallback',
                             proactive=bool(request and request['proactive']),
                             request_time_s=request['time_s'] if request else '',
                             forecast_gain_db=request['forecast_gain_db'] if request else '')
            events.append(event)

        xs = dict(samples[node, 'sumoX'])
        ys = dict(samples[node, 'sumoY'])
        if xs.keys() != ys.keys() or len(xs) < END_TIME * 10 - 2:
            raise ValueError(f'Incomplete position trace for {vehicle}')
        error = max(dist((x, ys[time]), positions[vehicle][round(time * 10)]) for time, x in xs.items())
        if error > 0.02:
            raise ValueError(f'{vehicle} SUMO and Simu5G positions differ by {error:.4f} m')

    events.sort(key=lambda event: event['time_s'])
    report = {'passed': True, 'simulated_seconds': END_TIME, 'verified_vehicles': len(mapping), 'handovers': events}
    if not sent or received > sent or len(delays) < 2:
        raise ValueError('Incomplete packet count or delay statistics')
    report['network'] = dict(sent=sent, received=received, delivery_percent=100 * received / sent,
                             p95_delay_ms=statistics.quantiles(delays, n=20, method='inclusive')[18],
                             rapid_returns=reversals)
    overload = 0
    for (node, name), series in samples.items():
        if name != 'avgServedBlocksDl:vector':
            continue
        for start in range(0, len(series), 100):
            slot_window = series[start:start + 100]
            if len(slot_window) == 100 and sum(value for _, value in slot_window) > 0.8 * 100 * 50:
                overload += 0.1
    report['network']['overload_cell_seconds'] = round(overload, 1)
    if policy:
        model_routes = {event['route'] for event in events if event['controller'] == 'trustgraph'}
        report['model_routes'] = sorted(model_routes)
        if model_routes != {'northbound', 'southbound', 'straight-chain', 'junction-turn'}:
            raise ValueError(f'Model-requested handovers did not cover all routes: {sorted(model_routes)}')
        report['model_requested'] = sum(event['controller'] == 'trustgraph' for event in events)
        report['proactive'] = sum(event['proactive'] for event in events)
    (directory / 'verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    with (directory / 'handover-events.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(events[0]))
        writer.writeheader()
        writer.writerows(events)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    verify(Path(sys.argv[1]))
