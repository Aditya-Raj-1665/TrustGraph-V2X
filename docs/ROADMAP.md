# Research milestones

The verified WSL demo runs a trained model live on the NITK campus map. Eight vehicles use four stations across three driving patterns. Docker has a separate validation status because image unpacking exceeded available disk space. [Campus run and verified results](SUMO_NR.md) · [Docker status](DOCKER.md)

## Original synthetic pipeline

1. Real SUMO signalized intersection and mobility export.
2. Separate synthetic network environment for rapid development.
3. False-position attack injection with isolated truth.
4. Observable bipartite graphs, temporal windows, future targets, and independent run splits.
5. Baseline and trust-aware graph/GRU models, checkpoint selection by validation loss, held-out metrics.
6. Controller with candidate eligibility, hysteresis, dwell time, capacity reservations, and uncertainty fallback.
7. Synthetic closed-loop matched-seed evaluation and external inference API.

## Verified cellular baseline

OMNeT++ 6.4.0, INET 4.7.0 and Simu5G 1.8.1 are built under WSL2. A moving
NR vehicle completed a conventional handover from gNB 1 to gNB 2, while a
stationary control stayed attached to gNB 1. See [the run instructions and
evidence](NETWORK_STACK.md).

## Verified SUMO and cellular co-simulation

A single SUMO car moved through Veins and completed a Simu5G handover from
gNB 1 to gNB 2 with packet delivery before and after the change. The run
verified the car's identity and synchronized position records. See the
[co-simulation run and evidence](SUMO_NR.md).

Use roadside gNBs as the initial interpretation of the project's RSUs. If RSUs instead host applications/edge compute behind the cellular network, model association and compute load separately from radio handover.

The verified run exports synchronized SUMO motion, NR signal quality, cell
resource-block utilization, and the exact handover event to one CSV. The
[simulator training and control milestone](NR_TRAINING_AND_CONTROL.md)
extends this to a batch with up to four vehicles and a live model that can
request or defer the simulator's handover candidate.

The eight-car congestion test verified queue buildup during periods when
the other cell had spare capacity. TrustGraph matched the load-aware rule,
reduced rapid return handovers relative to native control, and increased
total overload duration in this suite. The follow-up collected 12 runs across
light, moderate, and high demand, including a case with spare capacity at
gNB 2 after three cars moved. Retraining beat persistence on congested
development windows. An opt-in TrustGraph proposal completed a live handover
about one second earlier. It improved delivery relative to the development
baselines, with higher overload duration. The separate final comparison uses
new seeds and packet rates. See the [run commands and results](NR_TRAINING_AND_CONTROL.md).

## Optional extensions beyond the fixed campus scenario

- Extend the four-cell, eight-vehicle scenario to different network layouts and vehicle sets.
- Support arrivals and departures inside model windows, and quantify the effect of missing or stale beacons.
- Validate how well measured downlink resource utilization predicts queue delay at other traffic levels.
- Distinguish transient bad SINR, application outage and radio-link failure.
- Preserve serving-link identity throughout a label horizon; mask censored outcomes.
- Keep train/validation/test split by original run family, including attacked copies. Add held-out scenarios.

## Optional threat-model experiments

Add false velocity, false radio reports, packet dropping, and on/off attacks individually. For packet dropping, identify the attacker-controlled forwarding/transmission path. For on/off attacks, label active corrupted messages rather than every message from an attacker. Specify trusted infrastructure measurements and whether attackers can forge them.

The original synthetic pipeline uses a common onset. Campus training samples onset and duration per corrupted vehicle, using x-axis bias and jitter. Evaluate unseen corruption patterns independently and report clean-data costs alongside robustness. [Campus corruption setup](CAMPUS_MODEL.md#learning-targets-and-trust-gate)

Compare reactive control, persistence/load heuristics, the exact referenced QASP method, ordinary temporal GNN and TrustGraph. The professor's QASP paper/algorithm must be supplied before claiming reproduction. The included load-aware heuristic is not QASP.

Vary vehicle density, seeds, interference and attack prevalence (0%, 5%, 10%, 20%, 30%). Report uncertainty over runs and paired policy differences. Include trust-gate ablations and shuffled-trust controls. Avoid treating overlapping windows as independent experimental replicates.

## Further evaluation

Measure packet delivery ratio, latency percentiles, throughput, successful/failed handovers, ping-pong rate with a stated interval, outage duration, overload duration and load fairness from actual network events. Measure inference and bridge latency. Calibrate confidence with validation data and test timeout, missing-data and out-of-distribution fallback.

The campus demonstration already uses Surathkal OSM roads. PlutoSDR hardware-in-the-loop validation remains an optional extension.
