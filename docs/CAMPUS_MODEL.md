# Campus dataset, TrustGraph model and training

The four-cell campus checkpoint drives `nitk_ml` and `nitk_ml_gui`. The two-cell congestion study supplies an optional warm-start checkpoint and has its own datasets, feature distribution and evaluation. [Campus runbook](SUMO_NR.md) · [Two-cell experiments](NR_TRAINING_AND_CONTROL.md)

## Generate the data and train a candidate

Start with the pinned stack and the bundled campus road file copied to `outputs/nitk/road.net.xml`. The packaged checkpoint already enables the live demo. Follow this procedure to regenerate training data or train another checkpoint. [First-time setup](../README.md#first-time-setup-on-windows)

From Ubuntu in the repository root:

```bash
bash scripts/run_sumo_nr.sh nitk_collect
```

The runner collects seeds 2201 through 2212 sequentially with native Simu5G, eight SUMO vehicles and four cells. Each result directory under `outputs/nitk_collect/` contains `run.log` and `campus-meta.json`. The latter records the OMNeT++ seed set and the ordered gNB coordinates in the Veins frame. Scalar and vector recording are disabled for collection. The launcher writes into the same seed paths on subsequent collections.

The map, route templates and departure locations are shared. SUMO seed 0 is fixed. For each OMNeT++ seed, `seed % 3` selects a standard-car speed cap of 14, 15 or 16 m/s, a chain-car cap of 21, 22 or 23 m/s, and a per-flow packet interval of 4, 10 or 20 ms, respectively. Collection packets are 1,200 bytes. This design varies radio seed, speed and demand together. It does not independently cover arbitrary route geometry, vehicle counts or tower layouts.

From Windows PowerShell in the repository root:

```powershell
.\.venv\Scripts\python.exe -m trustgraph.nr_campus train outputs/nitk_collect outputs/nitk-training-candidate
```

The source directory must contain exactly the 12 expected `seed-*` entries. Training requires eight observed vehicle identities, four towers and telemetry through at least tick 349 for each trace. The default warm start is `outputs/nr-congestion-mae/trustgraph.pt`. The trainer loads its compatible weights when the file exists and initializes the new radio head at zero. Use `--warm-start PATH` with a compatible two-cell congestion checkpoint to select another warm start. When the specified file is absent, the trainer starts with a new model. For the original warm-start data and training path, see the [two-cell congestion retraining procedure](NR_TRAINING_AND_CONTROL.md#congestion-retraining-and-development-comparison).

Compare the candidate's `metrics.json` with the saved run. The launcher reads `outputs/nitk-training/trustgraph-campus.pt` by default. To test the candidate through the live controller, first preserve the current checkpoint and its metrics, then place the candidate checkpoint at that path and run the headless audit. Keep the candidate's metrics with its checkpoint. A different initialization, dependency build, network file or source log can lead to different weights and timings.

## Telemetry and temporal windows

- The policy bridge prints one `TRUSTGRAPH_CAMPUS` row per active vehicle every 100 ms. Fields in order are tick, NR UE ID, x and y in metres in the Veins frame, speed in m/s, serving gNB ID, and the four downlink load fractions. Each cell load is served resource blocks divided by 50 blocks per slot times the 100 observed slots. The same cell loads appear on all rows for that tick.
- The trace reader discards tick 1, which can precede the first road position. It sorts vehicle identities by NR UE ID and requires consecutive ticks with a stable vehicle set. The log uses one-based gNB IDs. The graph stores zero-based serving indices internally.
- The radio observation is the per-cell beacon quality from the NR connection log, expressed in dB. Simu5G labels it RSSI in the log, and the measured quantity used here is the beacon's mean per-band SINR. The parser rounds the beacon timestamp to a 100 ms tick. The `fresh` tensor preserves actual beacon arrivals, while the model's radio input carries the latest value forward. Missing links are masked. Live inference uses telemetry available at or before the request time, with the telemetry emission offset handled in the reader.
- Inputs contain 10 observations, or 0.9 s from the first observation to the last. Training strides by five ticks. Each observation has eight vehicle nodes and four cell nodes with possible edges between every vehicle and every cell.

| Tensor | Features in source order |
| --- | --- |
| Vehicle | x and y relative to the mean tower position, each divided by 1,200 m. Speed divided by 24 m/s. Finite-difference y velocity divided by 24 and clipped to ±2. Displacement-speed residual divided by 24 and clipped to [0, 5]. Serving beacon in dB divided by 100. Serving-beacon-present flag |
| Cell | Tower y relative to the mean tower y, divided by 1,200 m. Current downlink load fraction |
| Vehicle–cell edge | Beacon in dB divided by 100. Geometry-based range divided by 1,200 m. Serving-cell indicator |
| Edge mask | A finite beacon exists and the car has a serving cell |

The first sample of each input window zeroes the velocity and displacement-residual features that require a previous observation. Unavailable numeric beacon features use zero with an accompanying flag or edge mask.

## Learning targets and trust gate

| Head | Supervision |
| --- | --- |
| Radio forecast | For each known vehicle–gNB link, mean of fresh beacon samples during the next 20 ticks (2 s), divided by 100. The loss includes links with a known beacon at the input end and a fresh future observation |
| Serving-link risk | Whether the mean future beacon for the cell serving at the end of the input is below 40 dB. Uses the corresponding radio observation mask |
| Load | Actual cell load fraction 10 ticks (1 s) after the end of the history |
| False-position score | Whether the vehicle's reported x is corrupted at the input endpoint in the dataset copy |

Each seed has a clean copy and a synthetically corrupted copy. In the corrupted copy, three randomly selected vehicles each receive a signed 65–160 m x offset with 4 m standard-deviation Gaussian noise, over a randomly selected interval. The start is sampled in row indices 30 through 119 and duration in 80 through 149 samples. True radio, load, actual route and serving association stay those of the originating simulator trace. The training label is therefore simulated report corruption. The standard campus launch supplies normal simulator mobility telemetry. The trained score is a model output and has no reported campus F1, precision or calibration result.

The model uses separate vehicle, cell and edge encoders, plus GRU state per node. A local vehicle GRU computes the attack logit. Each outgoing vehicle message is weighted by `1 − sigmoid(attack_logit)` before masked aggregation at the cells. Cell state sends context back to the vehicle GRU. The radio head learns a residual over the last observed beacon using final vehicle and cell states and the edge embedding. The load head learns a bounded residual over the mean of the last five measured loads, with the prediction clipped to [0, 1]. [Model implementation](../trustgraph/model.py)

## Split, selection and reported numbers

| Split | OMNeT++ seed sets | Role |
| --- | --- | --- |
| Training | 2201–2208 | Fit model parameters |
| Validation | 2209–2210 | Choose the checkpoint by minimum radio MAE in dB plus load MAE in percentage points |
| Held out | 2211–2212 | Evaluate the selected checkpoint |

The split is by original simulation run. Both copies and all overlapping windows of one seed stay in the same split. Training runs on CPU with seed 2026, hidden width 32, 18 epochs, batch size 32, AdamW at 0.002, and gradient clipping to 5. The objective combines the two binary cross-entropy losses, load MSE weighted by 8 and masked normalized radio MSE weighted by 20.

Persistence uses the last observed link beacon and last observed cell load as the forecasts. TrustGraph and persistence are scored on the same 256 held-out windows from the two seeds, including clean and synthetically corrupted copies. The windows overlap and are grouped into two independent simulator runs.

| Held-out metric | TrustGraph | Persistence |
| --- | ---: | ---: |
| Two-second beacon MAE | 4.3583 dB | 5.8051 dB |
| One-second cell-load MAE | 2.1601 percentage points | 2.0723 percentage points |

The model reduced radio forecast error on these two held-out seeds. Persistence had lower load error. These measurements cover one map and a small seed set. The live closed-loop result is a separate demonstration of model-requested handover on seed 1001. It verifies functional integration, with unchanged packet delivery and delay relative to native in that run. The campus study did not include a held-out architecture ablation or a live false-position comparison. [Campus handover evidence](SUMO_NR.md#verified-live-results)
