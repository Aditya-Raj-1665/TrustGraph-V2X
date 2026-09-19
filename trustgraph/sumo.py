"""Real SUMO intersection and TraCI mobility export; no fabricated RF columns."""
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET


def binary(name):
    search = str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', '')
    result = shutil.which(name, path=search)
    if result:
        return result
    if os.environ.get('SUMO_HOME'):
        executable = Path(os.environ['SUMO_HOME']) / 'bin' / (name + ('.exe' if os.name == 'nt' else ''))
        if executable.exists():
            return str(executable)
    raise FileNotFoundError(f'{name} not found. Install project with [sumo] or set SUMO_HOME.')


def write_xml(path, root):
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)


def create_scenario(directory, vehicles=20, seed=42):
    if vehicles < 1:
        raise ValueError('vehicles must be positive')
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    nodes = ET.Element('nodes')
    ET.SubElement(nodes, 'node', id='C', x='0', y='0', type='traffic_light')
    for name, x, y in [('W', -500, 0), ('E', 500, 0), ('N', 0, 500), ('S', 0, -500)]:
        ET.SubElement(nodes, 'node', id=name, x=str(x), y=str(y))
    edges = ET.Element('edges')
    for name in ['W', 'E', 'N', 'S']:
        ET.SubElement(edges, 'edge', {'id': name + 'C', 'from': name, 'to': 'C', 'numLanes': '1', 'speed': '13.9'})
        ET.SubElement(edges, 'edge', {'id': 'C' + name, 'from': 'C', 'to': name, 'numLanes': '1', 'speed': '13.9'})
    write_xml(directory / 'intersection.nod.xml', nodes)
    write_xml(directory / 'intersection.edg.xml', edges)
    subprocess.run([binary('netconvert'), '--node-files', str(directory / 'intersection.nod.xml'),
                    '--edge-files', str(directory / 'intersection.edg.xml'), '--output-file', str(directory / 'intersection.net.xml')], check=True)
    routes = ET.Element('routes')
    ET.SubElement(routes, 'vType', id='car', accel='2.6', decel='4.5', length='5', minGap='2.5', maxSpeed='13.9')
    pairs = [('W', 'E'), ('E', 'W'), ('N', 'S'), ('S', 'N'), ('W', 'N'), ('S', 'E')]
    for index, (start, end) in enumerate(pairs):
        ET.SubElement(routes, 'route', id=f'r{index}', edges=f'{start}C C{end}')
    for i in range(vehicles):
        ET.SubElement(routes, 'vehicle', id=f'veh_{i:03d}', type='car', route=f'r{i % len(pairs)}', depart=str(i), departSpeed='0')
    write_xml(directory / 'intersection.rou.xml', routes)
    root = ET.Element('configuration')
    inputs = ET.SubElement(root, 'input')
    ET.SubElement(inputs, 'net-file', value='intersection.net.xml')
    ET.SubElement(inputs, 'route-files', value='intersection.rou.xml')
    timing = ET.SubElement(root, 'time')
    ET.SubElement(timing, 'step-length', value='0.1')
    random = ET.SubElement(root, 'random_number')
    ET.SubElement(random, 'seed', value=str(seed))
    write_xml(directory / 'intersection.sumocfg', root)
    return directory / 'intersection.sumocfg'


def collect(config_path, output, duration=180., gui=False):
    import traci
    if duration <= 0:
        raise ValueError('duration must be positive')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [binary('sumo-gui' if gui else 'sumo'), '-c', str(Path(config_path).resolve()), '--no-step-log', 'true']
    if gui:
        # Each simulation step represents 100 ms. Matching that with a 100 ms
        # GUI delay makes vehicle motion easy to inspect instead of finishing
        # the entire scenario in a few seconds.
        cmd.extend(['--delay', '100'])
    traci.start(cmd, label='trustgraph')
    connection = traci.getConnection('trustgraph')
    rows, ids, times = 0, set(), []
    try:
        with output.open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['time_s', 'vehicle_id', 'x_m', 'y_m', 'speed_mps', 'acceleration_mps2', 'heading_deg', 'lane_id'])
            while connection.simulation.getMinExpectedNumber() > 0 and connection.simulation.getTime() < duration:
                connection.simulationStep()
                t = connection.simulation.getTime()
                times.append(t)
                for vehicle in connection.vehicle.getIDList():
                    x, y = connection.vehicle.getPosition(vehicle)
                    writer.writerow([t, vehicle, x, y, connection.vehicle.getSpeed(vehicle),
                                     connection.vehicle.getAcceleration(vehicle), connection.vehicle.getAngle(vehicle),
                                     connection.vehicle.getLaneID(vehicle)])
                    rows += 1
                    ids.add(vehicle)
            completed = connection.simulation.getMinExpectedNumber() == 0
    finally:
        connection.close()
    report = {'source': 'SUMO/TraCI', 'rows': rows, 'vehicles': len(ids), 'completed': completed,
              'last_time_s': times[-1] if times else 0, 'wireless_data': False}
    output.with_suffix('.metadata.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report
