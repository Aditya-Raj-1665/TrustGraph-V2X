# Run and verify the NITK SUMO simulation

## Quick start

Run this from PowerShell in the repository root on a configured machine:

```powershell
wsl -d Ubuntu -- bash scripts/run_sumo_nr.sh nitk_ml_gui
```

Replace `Ubuntu` with the name shown by `wsl --list --verbose`. A fresh installation from the README typically uses `Ubuntu-24.04`. From an Ubuntu shell in the repository root, omit `wsl -d Ubuntu --`. From another Windows directory, pass the quoted absolute WSL path to the script, such as `'/mnt/c/Projects/TrustGraph-V2X/scripts/run_sumo_nr.sh'`. Keep the launching terminal open.

| Mode | What runs | Outputs |
| --- | --- | --- |
| `nitk_ml_gui` | Trained campus policy and live SUMO GUI | `outputs/nitk_ml/` |
| `nitk_ml` | Same policy, headless SUMO | `outputs/nitk_ml/` |
| `nitk_gui` | Native Simu5G handover and live SUMO GUI | `outputs/nitk/` |
| `nitk` | Native Simu5G handover, headless SUMO | `outputs/nitk/` |
| `nitk_collect` | 12 sequential native campus runs for training and evaluation | `outputs/nitk_collect/seed-2201/` through `seed-2212/` |

The 35-second limit is **simulation time**. Compilation, GUI pacing, and model-worker waits add wall time. After the GUI displays the final frame, press **Enter in the terminal that launched SUMO**. Wait for the verifier to print a report with `"passed": true` and for the terminal prompt to return before opening the newly exported files.

Each launch creates a separate WSL directory and compiles the local simulator adapter. It copies results to the mode's shared output directory after verification. The GUI and headless modes of the same controller share that destination. Back up evidence before repeating a run and use one launcher at a time. Screenshots and the saved native comparison can outlive later headless runs in the same folder. The runner generates a fresh verification report and handover CSV on success. It does not regenerate the native comparison JSON.

## First run from a source checkout

1. Complete the Windows and WSL setup in the [first-time guide](../README.md#first-time-setup-on-windows).
2. Copy the bundled map and checkpoint from `docker/assets/` to the following launcher paths. The bundled copies are included with the updated source. Git ignores the working copies under `outputs/`. [Copy commands and checksums](../README.md#6-put-the-bundled-map-and-model-where-the-wsl-launcher-expects-them)
3. Run `nitk_ml` as a headless check, then `nitk_ml_gui` for the visual run. To establish a separate native reference, use `nitk` or `nitk_gui`.

| Required on the Windows project drive | Purpose |
| --- | --- |
| `.venv/Scripts/python.exe` | Windows worker with PyTorch, NumPy and the local package |
| `outputs/nitk/road.net.xml` | NITK SUMO network. Every campus mode, including ML, collection, and native, reads this path |
| `outputs/nitk-training/trustgraph-campus.pt` | Frozen campus state dict. Required only for ML modes |

The verified road file SHA-256 is `8a30d7ef0721eda384f9925687ac35bf3f1ae667aeec5ca2d79d2d9894796785`. The verified model SHA-256 is `5476c1758d2f42f0a4b4832f9cda08b6909a3f5c69a4af22a8669ae6178cec1c`. Check both from PowerShell:

```powershell
Get-FileHash outputs/nitk/road.net.xml, outputs/nitk-training/trustgraph-campus.pt -Algorithm SHA256
```

A regenerated file may differ byte for byte. Use the hashes to identify the exact saved assets and the verifier to check a new simulation. The map snapshot is preferable to a fresh OSM download when reproducing exact timings.

### Build the road file

Use the bundled road network for the reference demo. To rebuild it independently, run these commands from the repository root in Ubuntu. If a local `campus.osm.xml` snapshot exists, this reuses it. Otherwise it fetches the bounding box once. The final command replaces the working road file, so save the current file first if you intend to compare versions.

```bash
mkdir -p outputs/nitk
if [[ ! -s outputs/nitk/campus.osm.xml ]]; then
  curl --fail --location 'https://api.openstreetmap.org/api/0.6/map?bbox=74.786,13.002,74.803,13.023' \
    -o outputs/nitk/campus.osm.xml
fi
"$HOME/trustgraph-tools/venv/bin/netconvert" --osm-files outputs/nitk/campus.osm.xml \
  --lefthand --keep-edges.by-vclass passenger --output-file outputs/nitk/road.net.xml
```

The route generator checks adjacent edge connections before starting the simulator. A newer OpenStreetMap extract might have changed edge IDs, lane lengths or connections. Use the verified network if available. For a deliberate map change, update the routes and geometry in `scripts/prepare_nitk_demo.py`, check the expected path of each car, and re-collect data before evaluating a checkpoint on the revised scenario. The mapped roads come from OpenStreetMap and the four station placements are configured for this experiment. [OpenStreetMap attribution](https://www.openstreetmap.org/copyright) · [SUMO network conversion](https://sumo.dlr.de/docs/netconvert.html)

### Obtain or train the model

Use the bundled checkpoint to reproduce the reference run. The campus runner loads the checkpoint at launch. To train a separate candidate, run `nitk_collect` and follow the training procedure. [Campus model guide](CAMPUS_MODEL.md)

## What to watch in SUMO

The labels RSU1 to RSU4 refer to the four simulated roadside gNBs. A car adopts the color of its current serving gNB. The colored line connects the car to that gNB and follows the vehicle as it moves. The color and endpoint change when the simulator reports a completed serving-cell change.

| Driving pattern | Cars | Expected associations |
| --- | --- | --- |
| Northbound NH 66 | `trust-car-1` to `trust-car-3` | RSU1 blue → RSU2 orange |
| Southbound NH 66 | `trust-car-4` to `trust-car-6` | RSU2 orange → RSU1 blue |
| Faster northbound NH 66 | `trust-car-7` | RSU1 blue → RSU2 orange → RSU3 purple |
| Eastbound turn from the highway | `trust-car-8` | RSU2 orange → RSU4 green |

Initial association is separate from a handover. Colors show which station serves the car. To determine who requested a switch, check the `controller` and `proactive` fields in the CSV.

## Verified live results

The retained ML and native runs used OMNeT++ seed set 1001, SUMO seed 0, the same road and route inputs, matching vehicle trajectories and the same packet offering. The nine completed changes below were all attributed to TrustGraph in the ML run.

| SUMO vehicle | Transition | ML request (s) | ML completion (s) | Native completion (s) | ML initiated target |
| --- | --- | ---: | ---: | ---: | --- |
| `trust-car-7` | 1 → 2 | 7.00001 | 7.05001 | 7.05001 | No |
| `trust-car-3` | 1 → 2 | 9.00001 | 9.05001 | 9.05001 | No |
| `trust-car-2` | 1 → 2 | 10.00001 | 10.05001 | 10.05001 | No |
| `trust-car-1` | 1 → 2 | 16.00001 | 16.05001 | 16.05001 | No |
| `trust-car-6` | 2 → 1 | 18.00001 | 18.05001 | 18.05001 | No |
| `trust-car-5` | 2 → 1 | 20.000021 | 20.050021 | 22.05001 | Yes |
| `trust-car-8` | 2 → 4 | 24.00001 | 24.05001 | 24.05001 | No |
| `trust-car-4` | 2 → 1 | 26.000021 | 26.050021 | 29.05001 | Yes |
| `trust-car-7` | 2 → 3 | 26.000021 | 26.050021 | 27.05001 | Yes |

For the six rows marked No, Simu5G nominated the candidate and TrustGraph approved the request. Both runs delivered all 13,481 application packets and had 5 ms p95 delay, zero rapid returns and zero overload cell-seconds. The useful difference observed on this lightly loaded map was earlier completion for three cars' transitions. The archived comparison is `outputs/nitk_ml/native-comparison.json`. See the [campus model guide](CAMPUS_MODEL.md) for held-out forecast performance and the [two-cell study](NR_TRAINING_AND_CONTROL.md) for congestion and false-position results.

## Verify a run and read its evidence

The launcher verifies the simulation reached 35 seconds, each SUMO vehicle matches a Simu5G node, and network and display vectors match once initial attachment is complete. It checks the expected station visits in order and at least one received packet before and after each completed switch. It compares Veins positions with a deterministic SUMO reference trajectory using the same route and clock alignment, with a 2 cm tolerance. The reference trajectory is regenerated because GUI shutdown can leave its floating-car data incomplete. The handovers, display vectors and packet measurements come from the live coupled run.

For ML, the verifier matches radio completion, displayed attribution and a model request for the same UE, source and target within the preceding 100 ms. It requires at least one model-requested completion for each of the four route IDs, with northbound and southbound represented separately. The exact count of nine and zero fallbacks are findings from the saved run.

| File under the run directory | Use |
| --- | --- |
| `handover-events.csv` | One row per serving-cell transition after initial attachment. ML rows include controller, proactive flag, request time and forecast gain in dB |
| `verification.json` | Checks, simulation duration, per-vehicle events and network metrics |
| `policy.jsonl`, `checkpoint.json` | ML inference records and SHA-256 identity of the checkpoint |
| `run.log`, `handover.vec`, `handover.sca` | Simulator logs, time-series vectors and scalar/parameter metadata |
| `road.net.xml`, `road.rou.xml`, `road.sumocfg`, `campus.add.xml`, `campus.gui.xml` | Network, vehicle routes, simulator and display settings |
| `sumo-fcd.xml`, `demo-expected.json` | Reference trajectory and expected visits keyed by SUMO vehicle ID |
| `campus-before.png`, `campus-handover.png` | GUI screenshots. The handover screenshot is updated on later switches |

To re-run verification, pass a **copy** of the results directory. The verifier rewrites its CSV and JSON in the supplied directory:

```powershell
Copy-Item outputs/nitk_ml outputs/nitk_ml-audit -Recurse
.\.venv\Scripts\python.exe scripts/verify_nitk_demo.py outputs/nitk_ml-audit
Import-Csv outputs/nitk_ml-audit/handover-events.csv | Format-Table vehicle,time_s,from_gnb,to_gnb,controller,proactive
```

Network metrics use unique received application packet sequence IDs per receiving car. The matched demo's configured packet size is 100 bytes, which the verifier uses to convert sender throughput scalars to counts. The p95 uses the inclusive quantile of application delay samples in milliseconds. A rapid return is a reversal of the preceding switch within two seconds. The overload metric sums 100 ms cell windows above 80% downlink resource-block utilization across all cells. These metrics apply to the fixed demo configuration. Changes to the packet size or resource capacity require corresponding verifier changes.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `wsl` cannot find Ubuntu or the script | Run `wsl --list --verbose`, use that distro name, and check the current project directory or the quoted absolute WSL path |
| Nix profile, `opp_env`, Veins headers or simulator libraries missing | Follow the [stack setup](NETWORK_STACK.md) in order. Inspect `~/trustgraph-simulators/install.log` for the initial build |
| Map copy fails or a route is disconnected | Check `outputs/nitk/road.net.xml`. Restore the saved map or check OSM route edges and geometry before running |
| Checkpoint or Windows Python missing | Check both paths above. From PowerShell, run `.\.venv\Scripts\python.exe -c "import torch, trustgraph"` |
| Worker does not become ready or model fallback appears | Inspect the new `outputs/nitk_ml/bridge.*/worker.log`, `run.log` and `policy.jsonl` for that run. Verify that the checkpoint is the campus state dict and that the Windows worker can import the package |
| Headless works, GUI is absent | Inspect WSLg and the distro's GUI support, verify the mode ends in `_gui`, and check `sumo-gui` in the WSL tools environment |
| Frame stops at 35 s and output files still look old | Press Enter in the launching terminal, then wait for verification to finish and the prompt to return |
| Report fails or changed paths are hard to diagnose | Start with the WSL work directory printed at launch. The runner prints the tail of the simulator log on failure. Check expected station visits, route geometry and the output of the verifier |
| Launch prints build output or disk usage grows | A new `~/trustgraph-simulators/sumo-nr.*` directory is created on every launch. The installed Nix store and simulator sources are reused. Windows ML runs also leave a separate `outputs/nitk_ml/bridge.*` directory with raw per-request files. Preserve current run evidence before cleaning older stopped work directories |

## Two-cell corridor scenario

The scenario uses the same two-base-station Simu5G topology as the baseline.
Veins starts SUMO
through its TraCI manager and creates an NR car in OMNeT++ for the SUMO
vehicle `trust-car`. The vehicle drives east at 15 m/s, and a server sends
downlink traffic while Simu5G makes conventional handover decisions.

Simu5G 1.8.1 prepares its bearer definitions during initialization, before
Veins creates the car. The scenario's bearer configurator loads the single
on-demand definition once the car has registered. The first downlink packet
then establishes the bearer through Simu5G's normal connection control.
This setup covers one vehicle whose route lasts the whole run.

For setup use the [simulator stack guide](NETWORK_STACK.md). After that, run the one-car integration test from Ubuntu:

```bash
bash scripts/run_sumo_nr.sh baseline
```

## Evidence

On 19 November 2026, the co-simulation reached 35 simulated seconds. The
SUMO vehicle `trust-car` appeared as `car[0]` in OMNeT++. Its 349 recorded
network positions matched the SUMO trajectory after coordinate and timestamp
conversion, with a maximum difference below one micrometre. Simu5G completed
the gNB 1 to gNB 2 handover at 16.05001 s. The car received 1,691 downlink
application packets, including packets before and after handover.

The runner compares the OMNeT++ car coordinates against SUMO's floating-car
data from the same run. It checks the vehicle ID and accounts for the Veins
coordinate transform and the two simulators' step timestamp conventions.
It also checks for a completed gNB 1 to gNB 2 transition with packet reception
before and after it. Passing runs are copied to `outputs/sumo-nr/` with
`positions.json`, `verification.json`, the simulator log and raw traces.

## Synchronized telemetry CSV

From the repository root, export the saved run with Python 3:

```bash
python3 scripts/export_sumo_nr.py outputs/sumo-nr
```

The resulting `outputs/sumo-nr/telemetry.csv` has 350 `sample` rows at
100 ms intervals from 0.1 s through 35.0 s and one `handover_completed` row
at 16.05001 s. Filter on `record_type == "sample"` to get a regular time series.
The event row preserves the original timestamp and source/target gNBs.

| Fields | Source and alignment |
| --- | --- |
| `sumo_x_m`, `sumo_y_m`, `sumo_speed_mps` | Original SUMO coordinates and speed. The FCD timestamp marks the start of each step and the OMNeT++ timestamp marks when TraCI makes the sample available, 100 ms later. |
| `serving_gnb` | Last NR serving-cell event at or before the row time. |
| `serving_dl_data_sinr_db`, `serving_dl_cqi` | Latest received downlink data measurement in the preceding 100 ms window for the current association. Each has its own timestamp. Empty fields indicate no qualifying measurement. |
| `gnbN_beacon_sinr_db` | Latest available per-cell beacon measurement at or before the sample, with its original timestamp. Simu5G labels this value RSSI in the log but computes it by averaging the beacon's per-band SINR values. Beacons in this run arrive once per second, so values repeat between updates. |
| `gnbN_dl_rb_utilization`, `gnbN_ul_rb_utilization` | Allocated resource blocks divided by total block capacity across the 100 completed 1 ms slots ending at the sample. Values are fractions from 0 to 1. This single downlink flow places little demand on either cell. |

At 16.0 s the car is still attached to gNB 1. The latest beacons show
32.3549 dB for gNB 1 and 42.6777 dB for gNB 2. The handover event follows
at 16.05001 s, and the 16.1 s sample shows gNB 2 serving the car. This integration trace preceded the [campus training runs](CAMPUS_MODEL.md) and the [two-cell congestion experiments](NR_TRAINING_AND_CONTROL.md).
