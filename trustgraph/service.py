"""Local HTTP inference boundary for an external simulator adapter.

The adapter still has to collect Simu5G measurements and execute/acknowledge
handover commands; this service itself does not implement cellular handover.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import numpy as np
from .controller import choose_targets
from .learning import Predictor

REQUIRED = {'time', 'vehicle_ids', 'reported_x', 'reported_y', 'speed', 'direction',
            'sinr', 'serving', 'load', 'since_handover'}


def validate_frames(frames, config):
    if not isinstance(frames, list) or not 1 <= len(frames) <= config.history:
        raise ValueError('frames must contain between 1 and history snapshots')
    parsed = []
    ids = None
    previous_time = None
    for frame in frames:
        if not REQUIRED <= frame.keys():
            raise ValueError(f'Missing fields: {sorted(REQUIRED - frame.keys())}')
        current_ids = frame['vehicle_ids']
        if not isinstance(current_ids, list) or not current_ids or len(set(current_ids)) != len(current_ids):
            raise ValueError('vehicle_ids must be a nonempty list of unique IDs')
        if ids is not None and current_ids != ids:
            raise ValueError('Vehicle identity/order must stay fixed throughout a window')
        ids = current_ids
        t = float(frame['time'])
        if not np.isfinite(t) or t < 0:
            raise ValueError('Invalid timestamp')
        if previous_time is not None and not np.isclose(t - previous_time, config.dt, atol=1e-5):
            raise ValueError('Snapshots must be ordered at the configured sampling interval')
        previous_time = t
        row = {'time': t, 'vehicle_ids': ids}
        for key in REQUIRED - {'time', 'vehicle_ids'}:
            value = np.asarray(frame[key], dtype=float)
            shape = (len(ids), 3) if key == 'sinr' else ((3,) if key == 'load' else (len(ids),))
            if value.shape != shape or not np.isfinite(value).all():
                raise ValueError(f'{key} must be finite and shaped {shape}')
            if key == 'serving':
                if np.any(value != np.floor(value)) or np.any((value < 0) | (value > 2)):
                    raise ValueError('serving must contain integer cell indices 0..2')
                value = value.astype(int)
            row[key] = value
        if np.any(row['load'] < 0) or np.any(row['speed'] < 0) or np.any(row['since_handover'] < 0):
            raise ValueError('Load, speed and handover age must be nonnegative')
        parsed.append(row)
    return parsed


def handle_request(payload, predictor):
    frames = validate_frames(payload['frames'], predictor.config)
    prediction = predictor(frames)
    targets = choose_targets(frames[-1], predictor.config, prediction)
    result = {'request_id': payload.get('request_id'), 'simulation_time': frames[-1]['time'],
              'valid_until': frames[-1]['time'] + predictor.config.dt,
              'vehicle_ids': frames[-1]['vehicle_ids'], 'target_cells': targets.tolist(),
              'mode': 'model_with_per_vehicle_fallback' if prediction else 'reactive_warmup',
              'model_source': 'toy-radio-NOT-Simu5G'}
    if prediction:
        result['predictions'] = {key: value.tolist() for key, value in prediction.items()}
    return result


def serve(checkpoint, port=8765):
    predictor = Predictor(checkpoint)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != '/predict':
                self.send_error(404)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2_000_000:
                    raise ValueError('Body must be 1..2000000 bytes')
                self.connection.settimeout(5)
                payload = json.loads(self.rfile.read(length))
                with lock:
                    result = handle_request(payload, predictor)
                status = 200
            except (ValueError, KeyError, TypeError, AttributeError, OSError) as error:
                result, status = {'error': str(error)}, 400
            encoded = json.dumps(result, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'Inference service: http://127.0.0.1:{port}/predict', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
