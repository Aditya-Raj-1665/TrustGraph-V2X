"""Prepare the campus and synthetic roadside handover demonstrations."""

import json
from math import dist
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

END_TIME = 35


def lane_position(network, edge, offset):
    lane = network.find(f"edge[@id='{edge}']/lane[@index='0']")
    points = [tuple(map(float, pair.split(','))) for pair in lane.attrib['shape'].split()]
    for start, end in zip(points, points[1:]):
        length = dist(start, end)
        if 0 < length and offset <= length:
            return tuple(a + (b - a) * offset / length for a, b in zip(start, end))
        offset -= length
    raise ValueError(f'Demo marker falls beyond edge {edge}')


def synthetic_network(work, scenario):
    if scenario == 'intersection':
        locations = {'west': (0, 400), 'center': (400, 400), 'east': (850, 400),
                     'south': (400, 60), 'north': (400, 820)}
        links = {'approach': ('west', 'center'), 'straight': ('center', 'east'),
                 'turn': ('center', 'north'), 'side-road': ('south', 'center')}
        routes = {'straight': ('approach', 'straight'), 'turn': ('approach', 'turn')}
        cars = [('straight', 45, [1, 2]), ('turn', 115, [1, 3])]
        towers = [(155, 368), (675, 368), (432, 660)]
        viewport = (430, 405, 105)
    else:
        locations = {'west': (0, 100), 'east': (1100, 100), 'south': (450, 0),
                     'north': (450, 200)}
        links = {'through': ('west', 'east'), 'side-road': ('south', 'north')}
        routes = {'through': ('through',)}
        cars = [('through', 55, [1, 2, 3]), ('through', 135, [1, 2, 3])]
        towers = [(105, 68), (423, 132), (746, 68)]
        viewport = (540, 105, 95)
    nodes, edges = ET.Element('nodes'), ET.Element('edges')
    for name, (x, y) in locations.items():
        ET.SubElement(nodes, 'node', id=name, x=str(x), y=str(y))
    for name, (source, target) in links.items():
        ET.SubElement(edges, 'edge', {'id': name, 'from': source, 'to': target, 'speed': '25'})
    ET.ElementTree(nodes).write(work / 'demo.nod.xml')
    ET.ElementTree(edges).write(work / 'demo.edg.xml')
    subprocess.run(['netconvert', '--node-files', 'demo.nod.xml', '--edge-files', 'demo.edg.xml',
                    '--lefthand', '--offset.disable-normalization', '--output-file', 'road.net.xml'],
                   cwd=work, check=True)
    return routes, cars, towers, viewport


def prepare(work, mode, seed=1001):
    gui = mode.endswith('_gui')
    scenario = mode.removesuffix('_gui')
    if scenario in ('nitk_collect', 'nitk_ml'):
        scenario = 'nitk'
    if scenario == 'nitk':
        routes = {'northbound': ('1351151584', '1205674608', '801453911#0', '801453911#1'),
                  'southbound': ('1152950802#0', '1152950802#1', '1351151586', '1351151587', '239322886')}
        routes['straight-chain'] = routes['northbound']
        routes['junction-turn'] = ('1152950802#0', '-1148873911', '1291688492', '-176064253#29',
                                   '-176064253#28', '-176064253#27', '-176064253#26', '-176064253#25')
        cars = [('northbound', pos, [1, 2]) for pos in (12, 72, 132)]
        cars += [('southbound', pos, [2, 1]) for pos in (220, 275, 330)]
        cars += [('straight-chain', 145, [1, 2, 3]), ('junction-turn', 370, [2, 4])]
        viewport = (965, 1820, 235)
    else:
        routes, cars, towers, viewport = synthetic_network(work, scenario)
    net = ET.parse(work / 'road.net.xml').getroot()
    connections = {(node.get('from'), node.get('to')) for node in net.findall('connection')}
    for edges in routes.values():
        if any(pair not in connections for pair in zip(edges, edges[1:])):
            raise ValueError(f'The NH 66 demo route starting at {edges[0]} is disconnected')

    root = ET.Element('routes')
    speed = str((14, 15, 16)[seed % 3] if mode == 'nitk_collect' else 15) if scenario == 'nitk' else '18'
    ET.SubElement(root, 'vType', id='vehicle', maxSpeed=speed, speedFactor='1', speedDev='0', sigma='0')
    if scenario == 'nitk':
        chain_speed = 21 + seed % 3 if mode == 'nitk_collect' else 22
        ET.SubElement(root, 'vType', id='chain-car', maxSpeed=str(chain_speed), speedFactor='1', speedDev='0', sigma='0')
    for name, edges in routes.items():
        ET.SubElement(root, 'route', id=name, edges=' '.join(edges))
    expected = {}
    # All vehicles join on the first step so their radio bearers can be configured together.
    for index, (route, position, cells) in enumerate(cars, 1):
        vehicle = f'trust-car-{index}'
        expected[vehicle] = {'route': route, 'cells': cells}
        chain = route == 'straight-chain'
        ET.SubElement(root, 'vehicle', id=vehicle, type='chain-car' if chain else 'vehicle', route=route,
                      depart='0', departPos=str(position), departLane='1' if chain else '0', departSpeed='max')
    ET.ElementTree(root).write(work / 'road.rou.xml')
    (work / 'demo-expected.json').write_text(json.dumps(expected, indent=2))

    config = ET.parse(work / 'road.sumocfg')
    config.getroot().remove(config.find('output'))
    ET.SubElement(config.find('input'), 'additional-files', value='campus.add.xml')
    device = ET.SubElement(config.getroot(), 'fcd_device')
    ET.SubElement(device, 'device.fcd.probability', value='0')
    ET.SubElement(device, 'device.fcd.explicit', value=','.join(expected))
    gui_section = ET.SubElement(config.getroot(), 'gui_only')
    ET.SubElement(gui_section, 'gui-settings-file', value='campus.gui.xml')
    config.write(work / 'road.sumocfg')

    # Convert the same marker coordinates to the corresponding Veins frame.
    min_x, min_y, max_x, max_y = map(float, net.find('location').attrib['convBoundary'].split(','))
    shapes = ET.Element('additional')
    if scenario == 'nitk':
        north = routes['northbound']
        towers = []
        for edge, offset, side in ((north[0], 12, -1), (north[2], 100, 1)):
            x, y = lane_position(net, edge, offset)
            towers.append((x + 45 * side, y))
        # gNB 3 extends NH 66 coverage. gNB 4 serves the road branching east.
        x, y = lane_position(net, north[3], 160)
        towers.append((x + 28, y))
        x, y = lane_position(net, '-176064253#29', 62)
        towers.append((x, y - 26))
    overrides = []
    for cell, ((x, y), color) in enumerate(zip(towers, ('35,125,255', '255,125,32', '120,65,205', '0,145,95')), 1):
        ET.SubElement(shapes, 'poi', id=f'gnb{cell}', type=f'RSU{cell}', color=color,
                      x=f'{x:.4f}', y=f'{y:.4f}', layer='15', width='14', height='14')
        overrides.extend([
            f'*.gnb{cell}.mobility.initialX = {x - min_x + 25:.4f}m',
            f'*.gnb{cell}.mobility.initialY = {max_y - y + 25:.4f}m',
        ])
    ET.ElementTree(shapes).write(work / 'campus.add.xml')
    if scenario == 'nitk':
        geometry = [[round(x - min_x + 25, 4), round(max_y - y + 25, 4)] for x, y in towers]
        (work / 'campus-meta.json').write_text(json.dumps({'seed': seed, 'towers': geometry}))

    view = ET.Element('viewsettings')
    scheme = ET.SubElement(view, 'scheme', name='TrustGraph demo')
    ET.SubElement(scheme, 'vehicles', vehicleMode='0', vehicle_exaggeration='1.5', vehicle_constantSize='1')
    ET.SubElement(scheme, 'pois', poiType_show='1', poiType_size='65', poiType_color='30,45,60',
                  poiType_bgColor='255,255,255,235', poiType_constantSize='1')
    ET.SubElement(scheme, 'legend', showSizeLegend='0', showColorLegend='0', showVehicleColorLegend='0')
    x, y, zoom = viewport
    ET.SubElement(view, 'viewport', zoom=str(zoom), x=str(x), y=str(y))
    ET.ElementTree(view).write(work / 'campus.gui.xml')

    ini = work / 'omnetpp.ini'
    baseline = ini.read_text()
    baseline = '\n'.join(line for line in baseline.splitlines() if not line.startswith((
        '*.gnb1.mobility.initialY', '*.gnb2.mobility.initialY',
        '*.veinsManager.moduleType', '*.veinsManager.moduleName',
        '*.car[0].', '*.server.numApps', '*.server.app[0].', 'sim-time-limit', 'seed-set', '**.cmdenv-log-level')))
    overrides.extend([
        f'sim-time-limit = {END_TIME}s',
        f'seed-set = {seed}',
        f'**.mobility.constraintAreaMaxX = {max_x - min_x + 50:.4f}m',
        f'**.mobility.constraintAreaMaxY = {max_y - min_y + 50:.4f}m',
        '*.car[*].servingNodeId = 0',
        '*.car[*].cellularNic.nrChannelModel[0].componentCarrierModule = "carrierAggregation.componentCarrier[0]"',
        '*.car[*].numApps = 1',
        '*.car[*].app[0].typename = "CbrReceiver"',
        '*.car[*].app[0].localPort = 3000',
        '*.car[*].mobility.showServingCell = true',
        '*.car[*].mobility.cmdenv-log-level = info',
        '*.car[*].cellularNic.rrc.nrConnectionControl.cmdenv-log-level = info',
        '*.policy.cmdenv-log-level = info',
        '**.cmdenv-log-level = warn',
        f'*.bearerConfigurator.expectedCars = {len(expected)}',
        f'*.server.numApps = {len(expected)}',
        '*.server.app[*].destAddress = "car[" + string(ancestorIndex(0)) + "]"',
        '*.server.app[*].startTime = 1.1s + ancestorIndex(0)*0.001s',
        '*.server.app[*].finishTime = 34.9s',
        '**.dynamicCellAssociation = false',
        '*.veinsManager.moduleType = "TrustGraphCar"',
        '*.veinsManager.moduleName = "car"',
        '*.veinsManager.seed = 0',
    ])
    if scenario == 'nitk':
        overrides.append('*.policy.campusTelemetry = true')
    if mode.startswith('nitk_ml'):
        overrides.extend([
            'cmdenv-autoflush = true',
            '*.policy.enabled = true', '*.policy.campusPolicy = true', '*.policy.responseTimeoutMs = 5000',
            '*.car[*].cellularNic.rrc.nrConnectionControl.typename = "PolicyConnectionControl"',
        ])
    if mode == 'nitk_collect':
        overrides.extend([
            '**.vector-recording = false', '**.scalar-recording = false',
            f'*.server.app[*].samplingTime = {(0.004, 0.01, 0.02)[seed % 3]}s',
            '*.server.app[*].packetSize = 1200B',
        ])
    for index, data in enumerate(expected.values()):
        overrides.append(f'*.car[{index}].nrServingNodeId = {data["cells"][0]}')
    if len(towers) >= 3:
        overrides.extend(['*.thirdCell = true', f'*.gnb*.numX2Apps = {len(towers) - 1}'])
        if len(towers) == 4:
            overrides.append('*.fourthCell = true')
        peers = range(1, len(towers) + 1)
        for source in peers:
            for app, target in enumerate(peer for peer in peers if peer != source):
                port = [peer for peer in peers if peer != target].index(source)
                overrides.append(f'*.gnb{source}.x2App[{app}].client.connectAddress = "gnb{target}%x2ppp{port}"')
    if gui:
        overrides.extend([
            '*.car[*].mobility.captureHandover = true',
            '*.veinsManager.holdFinalFrame = true',
            '*.veinsManager.command = "sumo-gui"',
            '*.veinsManager.commandLine = "$command --remote-port $port --seed $seed --configuration-file $configFile --start --delay 175 --window-size 1200,850"',
        ])
    ini.write_text(baseline + '\n' + '\n'.join(overrides) + '\n')


if __name__ == '__main__':
    prepare(Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 1001)
