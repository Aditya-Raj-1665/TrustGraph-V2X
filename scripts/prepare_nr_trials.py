"""Create deterministic, run-separated two-cell SUMO trials."""
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET


def prepare(root, stress=False, adaptive=None):
    advanced = stress or adaptive is not None
    trials = {'probe': range(30, 33), 'batch': range(40, 52), 'final': range(60, 66)}
    for trial in trials[adaptive] if adaptive else (range(20, 23) if stress else range(12)):
        directory = root / f'trial-{trial:02d}'
        directory.mkdir()
        for name in ('upstream.ini', 'demo.xml', 'road.sumocfg'):
            shutil.copyfile(root / name, directory / name)
        count = 8 if advanced else (1, 2, 4)[trial % 3]
        split_index = trial - 40 if adaptive == 'batch' else trial
        split = ('stress' if stress or adaptive == 'probe' else
                 ('train' if split_index < 6 else ('validation' if split_index < 9 else 'test')))
        if adaptive == 'final':
            split = 'final'
        reverse = not advanced and trial % 2 == 1
        speed = (10 + trial % 4) if advanced else (12, 15, 18, 21)[trial % 4]
        routes = ET.Element('routes')
        ET.SubElement(routes, 'vType', id='vehicle', maxSpeed=str(speed),
                      speedFactor='1', speedDev='0', sigma='0')
        ET.SubElement(routes, 'route', id='corridor', edges='westbound' if reverse else 'eastbound')
        if advanced:
            ET.SubElement(routes, 'vType', id='local', maxSpeed='2', speedFactor='1', speedDev='0', sigma='0')
        for car in range(count):
            local = advanced and car >= 3
            if advanced:
                position = 370 - 24 * car if not local else 225 - 18 * (car - 3)
            else:
                position = (425 if reverse else 225) - 18 * car
            ET.SubElement(routes, 'vehicle', id=f'trust-{car}', type='local' if local else 'vehicle',
                          route='corridor', depart='0', departLane=str(car % 2),
                          departPos=str(position), departSpeed=str(2 if local else speed))
        ET.ElementTree(routes).write(directory / 'road.rou.xml', encoding='unicode')
        (directory / 'road.edg.xml').write_text('''<edges>
    <edge id="eastbound" from="west" to="east" numLanes="2" speed="24"/>
    <edge id="westbound" from="east" to="west" numLanes="2" speed="24"/>
</edges>
''', encoding='utf-8')
        interval = 0.002 if stress else (0.02, 0.01, 0.005, 0.01)[trial % 4]
        payload = 1200 if advanced else 100
        bands = 8 if advanced else 50
        rates = [(0.010, 0.010), (0.008, 0.010), (0.006, 0.010)]
        level = trial % 3
        if adaptive == 'batch':
            level = (trial - 40) % 3
            rates = [(0.045, 0.065), (0.018, 0.028), (0.006, 0.010)]
        if adaptive == 'final':
            rates = ([(0.042, 0.060), (0.017, 0.026), (0.0082, 0.0095)] if trial < 63 else
                     [(0.048, 0.070), (0.019, 0.030), (0.0058, 0.0105)])
        local_interval, mobile_interval = rates[level] if adaptive else (interval, interval)
        if adaptive:
            interval = mobile_interval
        measures = '''*.policy.recordBacklog = true
*.policy.rbCapacity = 8
*.policy.responseTimeoutMs = 10000
*.policy.cmdenv-log-level = info
*.carrierAggregation.componentCarrier[0].numBands = 8
**.dynamicCellAssociation = false
**.servingCell:vector.vector-recording = true
**.avgServedBlocksDl:vector.vector-recording = true
**.cbrRcvdPkt:vector.vector-recording = true
**.cbrFrameDelay:vector.vector-recording = true
**.*DlBacklogBytes.vector-recording = true
**.vector-recording = false
''' if advanced else '**.vector-recording = true\n'
        if adaptive:
            measures = measures.replace('**.vector-recording = false',
                                        '**.sumoX.vector-recording = true\n'
                                        '**.sumoY.vector-recording = true\n'
                                        '**.vector-recording = false')
        per_flow = f'*.server.app[3..7].samplingTime = {local_interval}s\n' if adaptive else ''
        (directory / 'omnetpp.ini').write_text(f"""include ../omnetpp.ini

[Config Trial]
extends = TrustGraphVeins
seed-set = {1100 + trial}
output-scalar-file = handover.sca
output-vector-file = handover.vec
*.bearerConfigurator.expectedCars = {count}
*.car[*].servingNodeId = 0
*.car[*].nrServingNodeId = {2 if reverse else 1}
*.car[*].cellularNic.nrChannelModel[0].componentCarrierModule = "carrierAggregation.componentCarrier[0]"
*.car[*].numApps = 1
*.car[*].app[0].typename = "CbrReceiver"
*.car[*].app[0].localPort = 3000
*.server.numApps = {count}
*.server.app[*].destAddress = "car[" + string(ancestorIndex(0)) + "]"
*.server.app[*].startTime = 1.1s + ancestorIndex(0)*0.001s
*.server.app[*].finishTime = 34.9s
{per_flow}*.server.app[*].samplingTime = {interval}s
*.server.app[*].packetSize = {payload}B
*.configurator.config = xmldoc("demo.xml")
*.car[*].mobility.cmdenv-log-level = info
*.car[*].cellularNic.rrc.nrConnectionControl.cmdenv-log-level = info
{measures}""", encoding='utf-8')
        (directory / 'trial.json').write_text(json.dumps(
            dict(id=directory.name, split=split, cars=count, seed=1100 + trial,
                 speed_mps=speed, direction='west' if reverse else 'east',
                 offered_packet_interval_s=interval, local_packet_interval_s=local_interval,
                 load_level=('light', 'moderate', 'high')[level] if adaptive in ('batch', 'final') else None,
                 payload_bytes=payload,
                 blocks_per_slot=bands), indent=2), encoding='utf-8')


if __name__ == '__main__':
    options = sys.argv[2:]
    adaptive = next((mode for mode in ('probe', 'batch', 'final') if f'--adaptive-{mode}' in options), None)
    prepare(Path(sys.argv[1]), '--stress' in options, adaptive)
