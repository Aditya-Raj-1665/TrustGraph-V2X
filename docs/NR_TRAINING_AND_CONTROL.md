# TrustGraph training and live handover experiment

## Simulator data and prediction

The batch uses the pinned SUMO, Veins, INET, OMNeT++, and Simu5G stack documented
in [SUMO_NR.md](SUMO_NR.md). Twelve 35-second trials vary SUMO travel direction,
speed (12–21 m/s), vehicle count (1, 2 or 4), radio seed and downlink inter-packet
interval (5–20 ms). The route stays on the two-cell corridor. Every car departs
in the first step and stays in the network for the full observation period.

The loader matches SUMO vehicle IDs to Veins modules and reads the NR UE ID
from each module's recorded parameters. It checks the OMNeT++ position trace
against SUMO's FCD for every car after the initial attachment. Six whole runs
train the models, three select the checkpoints and three provide test results.
Copies with injected position bias and jitter stay in the original run's split.

The graph uses one second of reported position and motion, two per-cell beacon
measurements and downlink radio-block utilization. It predicts whether a new
serving-cell beacon in the next second falls below 40 dB, cell utilization one
second ahead, and whether a position report was modified. The link task masks
windows where the serving cell changes or no future beacon is available.
The 40 dB threshold is an experiment definition. It does not represent a
3GPP radio link failure. A separate baseline uses the same architecture
without the learned trust gate. Fixed rules use a current-beacon threshold,
load persistence and a kinematic inconsistency check.

## Live control

The Python worker receives the simulator's candidate and reads only mobility,
load and beacon observations available by that decision time. It combines
predicted link risk and load with the measured radio advantage to request or
defer a move. Simu5G's normal source-cell procedure handles accepted requests.
The bridge logs the request and checks the completed association. A timeout,
insufficient evidence or a second deferral uses the native procedure.

This version reviews candidates selected by Simu5G. It cannot originate a
handover before Simu5G detects a candidate. False-position tests modify the
coordinates in the policy worker. SUMO vehicle motion and Simu5G radio
measurements continue to use the physical positions.

## Reproduce

In Ubuntu WSL, from the project folder, generate the batch:

```bash
bash scripts/run_sumo_nr.sh batch
```

Use the batch directory printed by the runner. In PowerShell, train the models
and start the live worker:

```powershell
.\.venv\Scripts\python.exe -m trustgraph.nr_trials outputs/nr-trials.BATCH outputs/nr-training
.\.venv\Scripts\python.exe -m trustgraph.nr_policy outputs/nr-control outputs/nr-training
```

With the worker active, run the comparisons in Ubuntu WSL:

```bash
bash scripts/run_sumo_nr.sh closed
```

Use the suite directory printed by the runner. After the suite finishes, stop
the worker with Ctrl+C and summarize the results in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/summarize_nr_control.py outputs/nr-control/suite.SUITE
```

All models, simulation output, policy evidence, and metrics are generated
under the repository's ignored `outputs/` directory.

## Verified results

The 19 November 2026 batch matched 9,772 recorded vehicle positions across
the 12 physical simulations. The prediction test used 996 windows from
three held-out physical runs and their corrupted copies.

| Held-out method | Link F1 | Link AUROC | Attack F1 | Load MAE (fraction) |
| --- | ---: | ---: | ---: | ---: |
| Fixed rules | 0.209 | 0.875 | 0.882 | 0.000239 |
| Graph without trust | 0.188 | 0.871 | 0.981 | 0.003744 |
| TrustGraph | 0.164 | 0.874 | 0.983 | 0.004152 |

In the clean two-car trial, TrustGraph requested gNB 1 to gNB 2 for both
vehicles at 16.00001 simulated seconds. The serving-cell traces and Simu5G
completion logs put both handovers at 16.05001 s.

The final comparison ran 24 simulations across four policies, two corruption
conditions and three held-out scenarios. TrustGraph completed 16 requested
handovers, eight per condition. Every policy achieved 100% application packet
delivery and 5 ms p95 delay in this suite. All had eight completed handovers
per condition, zero return handovers within two seconds, and no overload
windows above 80% utilization. The largest downlink load observed in any
100 ms window was 0.92%, so these runs establish live policy integration.
They provide no evidence that TrustGraph improves load balancing under
congestion.

The final local evidence is in `outputs/nr-training/metrics.json` and
`outputs/nr-control/suite.BTmrae/summary.json`. A preliminary run exposed a
Windows file-sharing race. Native fallback completed the affected handovers.
The bridge now uses a unique response file per request, and the final run
had zero response timeouts.

## Congestion stress test

Use `bash scripts/run_sumo_nr.sh stress_probe` to run a matched native-policy
probe. Eight vehicles start on gNB 1. Three move toward gNB 2 and five stay
near gNB 1. Each cell has eight resource blocks per 1 ms slot. Downlink
applications send 1,200-byte payloads every 100 ms in the calm run and every
2 ms in the congested run. These are intentionally severe two-cell test
conditions.

The congestion probe used the same route, capacity, and seed as the calm
control. gNB 1 load exceeded 80% while gNB 2 was below 50% for 13.8 seconds.
gNB 1's downlink RLC backlog peaked at 68,474,687 bytes versus zero in the
calm run. Both cells eventually hit 100% downlink utilization. Application
packet delivery was 29.80% within the 35-second run, and p95 delay for packets
that arrived was 17,762.55 ms. The calm control delivered 99.96% with 13 ms
p95 delay.

At 10 s, the congested run specifically shows 100% downlink utilization
and 33,128,908 bytes pending on gNB 1, while gNB 2 has zero utilization and
zero backlog. The p95 delay of packets received by that time is 6,051.7 ms,
versus 11 ms in the calm run.

For matched policy tests, start the existing Python worker from the
reproduction steps above and run `bash scripts/run_sumo_nr.sh stress` in WSL.
The runner evaluates native handover, a rule using measured cell load, and
the previous TrustGraph checkpoint on three seeds. Pass the printed suite
directory to `scripts/summarize_nr_control.py`. The JSON includes per-cell
peak utilization and queue backlog, packet delivery, delay, overload
cell-seconds, and rapid return handovers. All overload durations use 100 ms
windows and count each cell separately. Queue measurements sum the pending
bytes in the downlink NR RLC UM transmit entities at the respective gNB.
The stress bridge waits up to 10 wall-clock seconds for a worker response.
The simulator does not advance during that wait, so its modeled packet
and handover times exclude worker turnaround.

The completed suite matched the number of generated packets across policies
for each seed. All three native runs had windows with gNB 1 above 80% and
gNB 2 below 50%. Results below are means over the three scenarios:

| Policy | Packet delivery by 35 s | p95 delay of delivered packets | Overload cell-seconds | Rapid returns within 2 s |
| --- | ---: | ---: | ---: | ---: |
| Native | 30.50% | 17.862 s | 48.83 | 1.33 |
| Measured load-aware rule | 30.65% | 17.897 s | 49.97 | 0 |
| TrustGraph | 30.65% | 17.897 s | 49.97 | 0 |

The two policies matched on these outcomes in every seed. Each completed
nine requested handovers and prevented the rapid returns observed with the
native policy. They did not reduce total overload duration or delay. The
light-traffic checkpoint saw at most 1.76% utilization during training and
underestimated load during saturation. This test keeps that checkpoint
fixed to measure its behavior on unseen load conditions.

The verified results are in `outputs/nr-control/suite.bXDLoU/summary.json`
for the congestion probe and `outputs/nr-control/suite.aSMrjN/summary.json`
for the matched suite. A preliminary comparison was stopped after observing
response timeouts under concurrent simulation. The matched suite used the
longer stress-only wall-clock response window and had zero timeouts.

## Congestion retraining and development comparison

`bash scripts/run_sumo_nr.sh adaptive_probe` runs three eight-car native
scenarios. Three cars travel toward gNB 2 and five stay near gNB 1. Each
cell has eight downlink resource blocks per 1 ms slot. The selected high-load
profile sends 1,200-byte packets every 6 ms to each local car and every 10 ms
to each traveling car. In trial 32, gNB 1 reached 100% utilization. The third
distinct car moved to gNB 2 at 19.05001 s. Of the following complete 100 ms
windows, 11.1 s had gNB 1 above 80% and gNB 2 below 80%. gNB 2 averaged
63.3% over the entire 15.9 s following that move. See
`outputs/nr-control/suite.oreYmN/summary.json`.

`bash scripts/run_sumo_nr.sh adaptive_batch` collects 12 native runs, four
at each load level. The highest observed utilization of either cell ranged
from 24.6% to 46.8% in the light group and from 56.4% to 62.8% in the moderate
group. Each high-load run reached 100%. Each split covers all three levels.
Trials 40–45 are for fitting, 46–48 for checkpoint selection, and 49–51 for
development testing. Clean and false-position windows from the same run
share a split. These scenarios provide development evidence before the
separate final evaluation.

From the repository root in PowerShell, train on the printed batch path.

```powershell
.\.venv\Scripts\python.exe -m trustgraph.nr_trials outputs/nr-control/suite.jMcMEv outputs/nr-congestion-mae --congestion
```

The target is utilization exactly one second later. Persistence predicts
the latest observed utilization. A congested example has more than 80%
utilization in the latest observation or target. The graph learns a bounded
correction to the previous 500 ms mean from the synchronized motion, radio,
association, and load history. Checkpoint and correction strength are
selected on validation runs. The first fit improved overall absolute error
from 4.40 to 3.93 percentage points but increased congested error from 4.95
to 4.99 points. The second fit explicitly weights absolute errors on
congested windows, and validation selection prioritizes models that improve
on persistence both overall and during congestion. Its report records that
same comparison on the development test split as `passed_forecast_gate`.

| One-second forecast | Overall MAE, percentage points | Congested MAE, percentage points |
| --- | ---: | ---: |
| Persistence | 4.40 | 4.95 |
| Trailing 500 ms mean | 3.95 | 5.09 |
| Graph without trust weighting | 3.83 | 4.43 |
| TrustGraph | 3.93 | 4.50 |

Congested examples come from one development run. The graph without trust
weighting scored slightly better on load. TrustGraph's absolute error over
all windows of the high-load run was 6.17 points versus 6.02 for persistence.
The complete forecast report is `outputs/nr-congestion-mae/metrics.json`.

Start the live worker in PowerShell with the revised checkpoint.

```powershell
.\.venv\Scripts\python.exe -m trustgraph.nr_policy outputs/nr-control outputs/nr-congestion-mae
```

With the worker running, `bash scripts/run_sumo_nr.sh adaptive_control`
compares native handover, the measured load-aware rule, and TrustGraph on
the three development runs, each with clean and false-position inputs. The
false-position variant modifies the vehicle reports supplied to the live
worker. Infrastructure radio and load measurements come from Simu5G.

All 18 runs completed with the same packet count within each matched scenario
and zero bridge timeouts. On the high-load run, the six runs produced the
following outcomes, which were identical across the two input conditions.

| Policy | Packet delivery | p95 delivery delay | Overload cell-seconds | Returns within 2 s |
| --- | ---: | ---: | ---: | ---: |
| Native | 95.45% | 2.606 s | 39.4 | 1 |
| Measured load-aware rule | 94.50% | 4.407 s | 39.9 | 0 |
| TrustGraph | 94.50% | 4.407 s | 39.9 | 0 |

TrustGraph and the rule recorded identical network outcomes throughout the
suite, in `outputs/nr-control/suite.FW0eJP/summary.json`. The high-load
beacon logs showed cases where gNB 2 had room and a viable measured signal
before the native candidate was offered.

`bash scripts/run_sumo_nr.sh adaptive_early` tests an opt-in earlier proposal
on the same development scenarios. It waits for the native beacon procedure
first and skips a proposal while a handover is in flight. The worker requires
two consecutive beacon rounds with a gNB 2 measurement of at least 40 dB and
within 3 dB of the serving signal. Both current and one-second forecast load
must put gNB 1 above 80% and gNB 2 at or below 60%. This leaves 20 percentage
points before the overload threshold. Proposals are limited to one attempt
per car and at least two seconds between attempts. Simu5G's native RRC still
prepares and executes accepted handovers.

In both high-load development runs, the guarded TrustGraph controller moved
UE 2051 from gNB 1 to gNB 2 at 10.050021 s. The native controller and ordinary
TrustGraph completed that vehicle's first move at 11.05001 s. At the earlier
decision, the target beacon measured 46.43 dB and TrustGraph forecast roughly
5% target utilization one second later. The early variant increased delivery
to 96.80% and brought p95 delay down to 4.327 s versus 4.407 s for the rule.
It also increased overload to 42.4 cell-seconds and kept rapid returns at
zero. On gNB 1, overload fell from 33.8 to 33.7 seconds. On gNB 2, it rose
from 6.1 to 8.7 seconds. Native handover had lower p95 delay and overload. The light and
moderate runs had no early proposals and reproduced ordinary TrustGraph's
outcomes. All six early runs had zero bridge timeouts. See
`outputs/nr-control/suite.e77Vz8/summary.json`.

`bash scripts/run_sumo_nr.sh adaptive_early_rule` uses the same early
candidate and radio checks with measured utilization as its forecast. This
isolates the effect of the learned forecast from the effect of earlier
candidate eligibility. In all six matched runs it produced the same network
outcomes as the early TrustGraph controller. On the high-load run it moved
UE 2051 at the same time. Measured gNB 2 utilization was 22.1% at the
decision, well below the 60% limit. The observed gain over the ordinary rule
came from adding the earlier proposal. See
`outputs/nr-control/suite.YmXv2L/summary.json`.

### Run the separate final comparison

Keep the PowerShell worker above running. From the repository root in WSL,
run the following command.

```bash
bash scripts/run_sumo_nr.sh adaptive_final
```

This runs six new seeds on the same two-cell corridor, with two scenarios
at each load level and different packet intervals from training. The two
high-load scenarios vary local demand to test whether moving the traveling
cars relieves the source under different loads. Each is run with clean and
false-position reports for native handover, the load-aware rule, TrustGraph,
and the early variants of the rule and TrustGraph, for 60 simulations in
total. These scenarios are outside the training and development splits. The simulator prints the
results directory at startup. After it finishes, generate the summary in
PowerShell.

```powershell
.\.venv\Scripts\python.exe scripts/summarize_nr_control.py outputs/nr-control/suite.REPLACE_ME
```

### Final evaluation results

Trials 60–65 used six new seeds on the same corridor. The worker used the
checkpoint from the congestion retrain throughout the comparison. The replay
forecast evaluation used the six final native traces, pairing clean windows
with synthetic false-position windows. The target is radio-resource
utilization one second later. Errors are in percentage points.

| Forecast | Overall MAE | Congested MAE |
| --- | ---: | ---: |
| Persistence | 4.96 | 6.49 |
| Trailing 500 ms mean | 4.55 | 6.34 |
| Graph without trust weighting | 4.55 | 5.90 |
| TrustGraph | 4.60 | 6.00 |

TrustGraph beat persistence overall and on congested windows. The graph
without trust weighting had lower error on both measures. The frozen weights,
per-scenario metrics, and sample counts are identified in
`outputs/nr-control/suite.RMgcbb/forecast.json`.

All 60 simulations completed. Every matched set generated the same number of
packets across policies. There were zero bridge timeouts or rejected requests.
The table shows the mean across the two high-load scenarios. The same values
were observed for clean and false-position inputs.

| Policy | Packet delivery | Mean of run p95 delays | Overload cell-seconds | Returns within 2 s per run |
| --- | ---: | ---: | ---: | ---: |
| Native, measured-load rule, and TrustGraph | 94.45% | 2.299 s | 28.50 | 0 |
| Early measured-load rule and early TrustGraph | 96.42% | 3.236 s | 31.15 | 0 |

Both early policies moved UE 2050 to gNB 2 at 9.050021 s in trial 62 and at
12.050021 s in trial 65. Native Simu5G completed those handovers at 13.05001 s
and 17.05001 s, respectively. Early proposals increased delivery in both
scenarios. In trial 62, they reduced gNB 1 overload by 1.4 seconds and increased
gNB 2 overload by 2.2 seconds. In trial 65, gNB 1 overload stayed at 33.8 seconds
and gNB 2 overload increased by 4.5 seconds. Total overload and packet delay
increased in both trials.

Across all six scenarios, the early policies delivered 98.61% of packets on
average, compared with 97.95% for the other policies. Native Simu5G had two
rapid returns per input condition across the six scenarios. The other policies
had zero. Ordinary TrustGraph and the ordinary rule tied on the measured
network outcomes. Early TrustGraph and the early rule also tied throughout.
The final evaluation therefore supports an improvement in load forecasting
relative to persistence and a delivery benefit from earlier eligibility, with
higher delay and overload. See `outputs/nr-control/suite.RMgcbb/summary.json`.
