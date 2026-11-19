# SUMO and Simu5G co-simulation

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

## Setup on Ubuntu WSL

Use the pinned stack from [NETWORK_STACK.md](NETWORK_STACK.md). Install SUMO in
the same WSL tools environment and extract Veins beside the simulator projects.
The following commands are for a first Veins setup.

```bash
~/trustgraph-tools/venv/bin/pip install eclipse-sumo==1.22.0
cd ~/trustgraph-simulators
curl -fLsS https://codeload.github.com/sommer/veins/tar.gz/refs/tags/veins-5.3.1 -o veins-5.3.1.tar.gz
tar -xzf veins-5.3.1.tar.gz
mv -T -n veins-veins-5.3.1 veins-5.3.1
```

From the TrustGraph-V2X repository in Ubuntu:

```bash
bash scripts/build_veins.sh
bash scripts/run_sumo_nr.sh
```

Veins 5.3.1 predates INET 4.7.0. The build script removes unused includes of
the former INET UDP control-info header from two Veins sample application
sources. The upstream compatibility warning remains visible. The runner builds
and runs in a fresh Linux directory to keep paths with spaces out of the linker.

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
at 16.05001 s, and the 16.1 s sample shows gNB 2 serving the car. This run
provides an integration trace for adapting the feature schema. Training and
load balancing evaluation require more vehicles and independent runs.
