# Simulator inference boundary

The implemented HTTP service accepts observable history and returns proposed cell selections. It does not collect Simu5G data, modify the serving gNB, or acknowledge successful handovers. A C++/OMNeT++ adapter must implement those operations before this becomes real network co-simulation.

## Start and request

```powershell
.\.venv\Scripts\python.exe -m trustgraph serve --checkpoint outputs/demo/trustgraph/model.pt --port 8765
```

Send `POST http://127.0.0.1:8765/predict` with `Content-Type: application/json`:

```json
{
  "request_id": "run17-step0",
  "frames": [{
    "time": 0.0,
    "vehicle_ids": ["veh_000"],
    "reported_x": [-300.0],
    "reported_y": [8.0],
    "speed": [15.0],
    "direction": [1.0],
    "sinr": [[19.0, 9.0, -11.0]],
    "serving": [0],
    "load": [0.111111, 0.0, 0.0],
    "since_handover": [5.0]
  }]
}
```

The initial interface intentionally supports the toy layout: three cells at x = -400, 0, 400 metres and y = 0. Positions are metres, speed is metres/second, SINR is dB, timestamps/ages are seconds, cell indices are zero-based. `direction` is the x-axis motion sign in the one-dimensional toy road. Do not pass arbitrary curved-road headings into this feature: the feature schema must be extended and models retrained first.

Each frame contains the same ordered vehicle IDs. Send 1–10 frames at 100 ms intervals. Short histories use the reactive warmup policy. A full window enables the model and the per-vehicle certainty fallback. The service rejects nonfinite radio values, wrong shapes, duplicate IDs, changed identities, negative ages, and inconsistent time spacing. Inference is serialized to avoid concurrent model access.

Responses include:

- `request_id`, `simulation_time`, and `valid_until` for matching and freshness checks.
- Ordered `vehicle_ids` and `target_cells` (including unchanged cells).
- `mode`: `reactive_warmup` or `model_with_per_vehicle_fallback`.
- `predictions` for full windows: serving-link risk, cell load, and attack probability.
- `model_source`: explicitly `toy-radio-NOT-Simu5G`.

The adapter must reject an expired or mismatched response and use conventional handover. It must translate target indices to actual gNB identifiers, verify that targets remain reachable, request handover through the supported mechanism of the pinned Simu5G release, then log the actual completion/failure. A proposed command is never a successful handover measurement.

## Real simulator integration prerequisites

1. Choose a compatible OMNeT++, INET, Simu5G, Veins and SUMO set, and record exact versions. The current local SUMO wheel is for the standalone traffic milestone and is not asserted compatible with a future Veins build.
2. Run the standard Simu5G NR example and a two-gNB handover before introducing Python.
3. Build `veins_inet`, enable the Simu5G Cars feature, and verify the provided `simulations/nr/cars` scenario.
4. Export synchronized, timestamped vehicle and candidate-link observations, cell resource utilization, and handover events. Document whether each value is vehicle-reported or receiver-measured.
5. Extend graph identity/masking to vehicle arrivals/departures, arbitrary cell coordinates, missing candidate measurements, and real 2D motion. Keep true coordinates and attack labels outside inference payloads.
6. Generate new datasets, freeze target definitions, train new checkpoints, and calibrate thresholds. A toy-trained checkpoint is not a validated 5G predictor.
7. Connect the adapter to this API, account for inference/communication delay in simulation time, and measure completed handovers under matched-seed baselines.

On Windows, the documented Veins 5.3.1 integration with other module libraries uses WSL. Simu5G's `opp_env` path also supports Windows through WSL2. The Ubuntu installation here was checked; `opp_env`, `opp_run`, and `sumo` were not on its PATH.

Sources: [Simu5G installation and Cars integration](https://simu5g.org/install), [Veins compatibility](https://veins.car2x.org/download/).
