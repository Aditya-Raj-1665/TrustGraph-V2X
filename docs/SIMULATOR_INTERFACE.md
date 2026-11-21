# Simulator integration and inference interfaces

## Live campus control path

1. SUMO advances road traffic. Veins exchanges state via TraCI every 100 ms, creates OMNeT++ car modules, and maps SUMO coordinates into INET's local frame. The mapping uses the network bounds, flips the y-axis, and adds a 25 m margin.
2. Simu5G models the NR links and downlink traffic. The four gNBs have X2 connectivity configured by the scenario generator. An on-demand bearer configuration is prepared when the cars register in the first SUMO step.
3. The C++ policy bridge logs each vehicle's mobility, current gNB, and recent scheduled downlink resource utilization. The Python worker reads that log and the NR beacon reports to build its causal ten-sample graph. [Campus telemetry and feature schema](CAMPUS_MODEL.md#telemetry-and-temporal-windows)
4. When Simu5G supplies a handover candidate, the Python policy can request it or defer it. The campus adapter also checks for its own proactive opportunities on a one-second review schedule starting at 2 simulated seconds, just after the native beacon review. Pending handovers and recent completions gate proactive review.
5. The C++ adapter invokes Simu5G's RRC handover function. A request and a scheduled trigger are intermediate states. The serving-cell signal is the actual change observed by the GUI and verifier. `RecordedMobility` records and applies the color and line of the serving gNB through TraCI.

| Source | Responsibility |
| --- | --- |
| `scripts/run_sumo_nr.sh` | Select the scenario, build the adapter, manage the model worker and export verified results |
| `scripts/prepare_nitk_demo.py` | Generate routes, tower coordinates, SUMO display settings and network configuration overrides |
| `simulations/veins/TrustGraphRoad.ned` and `omnetpp.ini` | Network topology, mobility manager, policy configuration and inherited traffic scenario |
| `simulations/veins/PolicyBridge.cc` | Measurement logging, request/response protocol, candidate approval, proactive review and completion attribution |
| `simulations/veins/RecordedMobility.cc` | Bearer setup, SUMO identity, positions and serving-cell display |
| `simulations/veins/PresentationManager.cc` | Keep the final frame visible and close TraCI when the viewer finishes |
| `trustgraph/nr_campus.py` and `model.py` | Telemetry parsing, training, graph inference and constrained target ranking |
| `scripts/verify_nitk_demo.py` | Match request, actual switch, SUMO display, motion and packets |

### Live worker protocol

The verified WSL workflow starts the Windows Python worker automatically. Each live ML invocation creates `outputs/nitk_ml/bridge.XXXXXX/` and links it into the WSL work directory. The worker reads tower geometry from `campus-meta.json`, loads the state dict on CPU, writes the model identity to `checkpoint.json` and creates `ready`. The runner allows up to approximately 30 wall-clock seconds for readiness, checking every 200 ms while the worker is running. After simulation, the runner writes `stop` and waits for the worker to exit. The Docker recipe selects a Linux Python worker and mounts the corresponding result path under `outputs/docker/`. [Docker validation status](DOCKER.md)

| File or record | Campus contract |
| --- | --- |
| `request-N.txt` | `N sim_time ue serving candidate` for native-candidate review. Proactive review sends candidate `0` followed by `campus`. IDs in this protocol are simulator IDs |
| `response-N.txt` | `N decision` for native review. A proactive `request` appends the selected target gNB and its observed beacon strength |
| `run.log` | Flushed simulator output consumed by the worker, including timing, mobility, candidate beacons and completion markers |
| `policy.jsonl` | One inference record per processed request with time, UE, serving cell, native candidate and decision. Eligible predictions include forecast dB and load vectors, serving risk and false-position score. Successful proposals include target, measured dB, forecast gain and score |

Request and reply writers publish complete messages by renaming temporary files. The C++ side checks the sequence number. The bridge polls for a reply for up to five seconds of wall time per request in campus mode. That wait does not advance simulation time. The protocol has no HTTP server and the wait is not a simulated latency measurement.

### Policy and fallback

The model scores an alternative as forecast link gain in dB plus four times predicted serving risk, minus 30 times the difference between target and serving forecast loads. Both paths require a target beacon of at least 36 dB, forecast load at most 82%, and measured load at most 85%. They exclude the serving cell.

Native nominee review also checks relative signal, projected range, and a minimum score of −2. A deferral cancels that candidate once before the adapter can fall back on a later native trigger. Insufficient history, mismatched serving state, or missing beacon data can produce fallback decisions. Bridge I/O errors and timeouts also use the native path during review of a native nomination.

Proactive review requires two recent beacon observations, relative signal checks, forecast gain of at least 2 dB, score of at least 4, and projected range near the closest tower. The C++ side validates the selected gNB and beacon value before requesting the normal handover trigger. A missing or unusable proactive reply results in no proactive switch. The adapter suppresses proactive proposals for three simulated seconds after completion. In the same three-second interval it also suppresses some native nominees when the serving link is usable and the new signal gain is small. [Threshold implementation](../trustgraph/nr_campus.py) · [RRC adapter](../simulations/veins/PolicyBridge.cc)

The worker sets `proactive` on records from proactive review, including checks that return `keep`. The exported event CSV sets `proactive` only on a matched completed handover. Inspect `TRUSTGRAPH_REQUEST_COMPLETED` together with the RRC serving-cell vector and the worker output to establish attribution. The false-position prediction weights graph messages through the trust gate. The controller does not apply a separate attack-score cutoff to the final decision. [Live verification](SUMO_NR.md#verify-a-run-and-read-its-evidence)

## Original synthetic HTTP service

This optional service accepts toy-layout observations and returns proposed cell indices. It is a separate entry point from the campus worker.

### Start and request

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

Each frame contains the same ordered vehicle IDs. The default checkpoint configuration uses up to 10 frames at 100 ms intervals. Short histories use the reactive warmup policy. A full window enables the model and the per-vehicle certainty fallback. The service rejects nonfinite radio values, wrong shapes, duplicate IDs, changed identities, negative ages, and inconsistent time spacing. Inference is serialized to avoid concurrent model access.

Responses include:

- `request_id`, `simulation_time`, and `valid_until` for matching and freshness checks.
- Ordered `vehicle_ids` and `target_cells` (including unchanged cells).
- `mode`: `reactive_warmup` or `model_with_per_vehicle_fallback`.
- `predictions` for full windows: serving-link risk, cell load, and attack probability.
- `model_source`: explicitly `toy-radio-NOT-Simu5G`.

The adapter must reject an expired or mismatched response and use conventional handover. It must translate target indices to actual gNB identifiers, verify that targets remain reachable, request handover through the supported mechanism of the pinned Simu5G release, then log the actual completion/failure. A proposed command is never a successful handover measurement.
