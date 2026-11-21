"""Export the verified single-car SUMO/Veins/Simu5G timeline."""
import argparse
from bisect import bisect_right
import csv
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from verify_nr_handover import serving_cells, vector_samples


NODE = 'car[0]'
VEHICLE = 'trust-car'
CELLS = (1, 2)
BEACON = re.compile(r'UE (\d+) broadcast frame from (\d+) with RSSI: (\S+) at (\S+)')
HANDOVER = re.compile(r'\[INFO\]\s+(\S+) .*::doHandover - UE (\d+) has completed handover to eNB (\d+)')


def radio_log(log, transitions):
    completions = [(float(time), ue, int(cell)) for time, ue, cell in HANDOVER.findall(log)]
    if [(time, cell) for time, _, cell in completions] != [
        (time, target) for time, _, target in transitions
    ] or not completions:
        raise ValueError('Handover log and serving-cell vector disagree')
    ue_ids = {ue for _, ue, _ in completions}
    if len(ue_ids) != 1:
        raise ValueError('Expected one NR vehicle in the handover log')
    ue_id, = ue_ids
    beacons = {cell: [] for cell in CELLS}
    for ue, cell, value, time in BEACON.findall(log):
        if ue == ue_id and int(cell) in beacons:
            beacons[int(cell)].append((float(time), float(value)))
    if any(not values for values in beacons.values()):
        raise ValueError('Missing candidate-cell beacons')
    return ue_id, beacons


def last_at(series, time, after=None):
    index = bisect_right(series, (time, math.inf)) - 1
    if index >= 0 and (after is None or series[index][0] > after):
        return series[index]
    return None, None


def window_load(vector, cell, direction, blocks_per_slot, ticks):
    samples = vector_samples(vector, '.cellularNic.mac',
                             f'avgServedBlocks{direction}:vector', f'gnb{cell}')
    expected = ticks * 100  # 100 slots of 1 ms in each 100 ms interval.
    if len(samples) != expected or any(
        abs(time - index / 1000) > 1e-9 or not 0 <= blocks <= blocks_per_slot
        for index, (time, blocks) in enumerate(samples, 1)
    ):
        raise ValueError(f'Incomplete or invalid slot statistics for gNB {cell} {direction}')
    return [
        sum(blocks for _, blocks in samples[start:start + 100]) / (100 * blocks_per_slot)
        for start in range(0, expected, 100)
    ]


def export(directory, verify_display=False):
    log = (directory / 'run.log').read_text(encoding='utf-8')
    vector = directory / 'handover.vec'
    with vector.open(encoding='utf-8') as stream:
        run = next((m for line in stream if (m := re.fullmatch(r'run (\S+)\s*', line))), None)
    if run is None or f'Assigned runID={run[1]}' not in log:
        raise ValueError('Simulator log and vector belong to different runs')
    finish = re.search(r'Simulation time limit reached -- at t=(\d+(?:\.\d+)?)s', log)
    if finish is None or float(finish[1]) != 35:
        raise ValueError('Expected a completed 35-second run')

    association = serving_cells(vector, NODE)
    if not association or association[0] != (0.1, 1) or any(cell not in CELLS for _, cell in association):
        raise ValueError('Unexpected NR association sequence')
    if verify_display:
        displayed = vector_samples(vector, '.mobility', 'displayedServingCell', NODE)
        # The initial color is applied on the first mobility callback after
        # attachment. Subsequent changes come directly from the RRC signal.
        if (not displayed or displayed[0][1] != association[0][1]
                or not 0 <= displayed[0][0] - association[0][0] <= 0.100001
                or displayed[1:] != association[1:]):
            raise ValueError('SUMO display and Simu5G serving-cell changes disagree')
    transitions = [(time, source, target) for (_, source), (time, target)
                   in zip(association, association[1:]) if source != target]
    ue_id, beacons = radio_log(log, transitions)
    if [(source, target) for _, source, target in transitions] != [(1, 2)]:
        raise ValueError('Expected one completed handover from gNB 1 to gNB 2')

    with vector.open(encoding='utf-8') as stream:
        iterations = dict(
            (fields[1], fields[2]) for line in stream
            if line.startswith('itervar ') and len(fields := line.split()) == 3
        )
    blocks = int(iterations['numRbs'])
    if iterations['u'] != '0' or blocks <= 0:
        raise ValueError('Expected positive cell capacity and numerology 0 (1 ms slots)')

    ticks = 350
    loads = {f'gnb{cell}_{direction.lower()}_rb_utilization':
             window_load(vector, cell, direction, blocks, ticks)
             for cell in CELLS for direction in ('Dl', 'Ul')}
    measurements = {
        'serving_dl_data_sinr_db': vector_samples(
            vector, '.nrChannelModel[0]', 'rcvdSinrDl:vector', NODE),
        'serving_dl_cqi': vector_samples(vector, '.nrPhy', 'averageCqiDl:vector', NODE),
    }
    if any(not values for values in measurements.values()):
        raise ValueError('Missing serving-cell radio measurements')

    sumo = {}
    for step in ET.parse(directory / 'sumo-fcd.xml').iter('timestep'):
        for car in step.findall('vehicle'):
            if car.get('id') != VEHICLE:
                raise ValueError('Unexpected SUMO vehicle identity')
            time = float(step.attrib['time'])
            # FCD labels the step start, while the completed TraCI update
            # is available in OMNeT++ at the step end.
            tick = round(time * 10) + 1
            if tick in sumo or abs(time - (tick - 1) / 10) > 1e-9:
                raise ValueError('Unexpected SUMO timestamp')
            sumo[tick] = (time, float(car.attrib['x']), float(car.attrib['y']),
                          float(car.attrib['speed']))
    if set(sumo) != set(range(1, ticks + 1)):
        raise ValueError('Expected one SUMO sample per 100 ms from 0.1 to 35 s')

    identity = {'run_id': run[1], 'vehicle_id': VEHICLE, 'network_node': NODE, 'nr_ue_id': ue_id}
    rows = []
    for tick in range(1, ticks + 1):
        time = tick / 10
        sumo_time, x, y, speed = sumo[tick]
        attached_at, cell = last_at(association, time)
        row = dict(identity, record_type='sample', sim_time_s=time, sumo_fcd_time_s=sumo_time,
                   sumo_x_m=x, sumo_y_m=y, sumo_speed_mps=speed, serving_gnb=cell,
                   rb_capacity_per_slot=blocks, **{key: values[tick - 1] for key, values in loads.items()})
        # Use only measurements in this window from the current association.
        after = max((tick - 1) / 10, attached_at)
        for key, series in measurements.items():
            row[f'{key}_time_s'], row[key] = last_at(series, time, after)
        for gnb, series in beacons.items():
            row[f'gnb{gnb}_beacon_time_s'], row[f'gnb{gnb}_beacon_sinr_db'] = last_at(series, time)
        rows.append(row)
    for time, source, target in transitions:
        rows.append(dict(identity, record_type='handover_completed', sim_time_s=time,
                         serving_gnb=target, handover_from_gnb=source, handover_to_gnb=target))
    rows.sort(key=lambda row: row['sim_time_s'])
    fields = list(dict.fromkeys(key for row in rows for key in row))
    target = directory / 'telemetry.csv'
    with target.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='Directory with the verified co-simulation outputs')
    parser.add_argument('--verify-display', action='store_true', help='Verify the SUMO overlay update times')
    args = parser.parse_args()
    print(export(args.directory, args.verify_display))
