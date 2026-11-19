"""Compare the TraCI-driven OMNeT++ positions with the same SUMO run's FCD."""
import json
from math import hypot
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from verify_nr_handover import vector_samples


def main(directory):
    trace = directory / 'handover.vec'
    recorded_x = dict(vector_samples(trace, '.mobility', 'sumoX', 'car[0]'))
    recorded_y = dict(vector_samples(trace, '.mobility', 'sumoY', 'car[0]'))
    if recorded_x.keys() != recorded_y.keys():
        raise ValueError('The network position vectors have different timestamps')

    bounds = ET.parse(directory / 'road.net.xml').find('location').attrib['convBoundary']
    min_x, _, _, max_y = map(float, bounds.split(','))
    sumo = {}
    for step in ET.parse(directory / 'sumo-fcd.xml').iter('timestep'):
        for vehicle in step.findall('vehicle'):
            if vehicle.attrib['id'] != 'trust-car':
                raise ValueError('Unexpected vehicle in SUMO trajectory')
            # SUMO labels FCD samples with the start of the completed 100 ms
            # step. Veins records them when TraCI returns at the end of that step.
            tick = round(float(step.attrib['time']) * 10) + 1
            sumo[tick] = (float(vehicle.attrib['x']) - min_x + 25,
                          max_y - float(vehicle.attrib['y']) + 25)

    errors = []
    for time, x in recorded_x.items():
        tick = round(time * 10)
        if abs(time - tick / 10) > 1e-8 or tick not in sumo:
            raise ValueError(f'No matching SUMO sample for network timestamp {time}')
        expected_x, expected_y = sumo[tick]
        errors.append(hypot(x - expected_x, recorded_y[time] - expected_y))

    if len(errors) < 340 or max(errors) > 0.02:
        raise ValueError(f'Position verification failed: {len(errors)} samples, '
                         f'maximum error {max(errors, default=float("inf")):.6f} m')
    report = {
        'sumo_vehicle': 'trust-car',
        'network_module': 'car[0]',
        'compared_samples': len(errors),
        'first_network_time_s': min(recorded_x),
        'last_network_time_s': max(recorded_x),
        'max_position_error_m': max(errors),
        'position_tolerance_m': 0.02,
    }
    (directory / 'positions.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
