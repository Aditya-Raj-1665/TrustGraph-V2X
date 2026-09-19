# Research milestones

## Implemented and executable

1. Real SUMO signalized intersection and mobility export.
2. Separate synthetic network environment for rapid development.
3. False-position attack injection with isolated truth.
4. Observable bipartite graphs, temporal windows, future targets, and independent run splits.
5. Baseline and trust-aware graph/GRU models, checkpoint selection by validation loss, held-out metrics.
6. Controller with candidate eligibility, hysteresis, dwell time, capacity reservations, and uncertainty fallback.
7. Synthetic closed-loop matched-seed evaluation and external inference API.

## Next: real cellular simulation

Acceptance: a SUMO-driven vehicle changes serving gNB in Simu5G, with synchronized traffic, radio and handover event logs. A Python model command must cause an actual completed handover; a returned target index alone does not satisfy this milestone.

Use roadside gNBs as the initial interpretation of the project's RSUs. If RSUs instead host applications/edge compute behind the cellular network, model association and compute load separately from radio handover.

The software libraries need installation/building under WSL and validation as a compatible set. No uncompiled placeholder C++ adapter is presented as a completed simulator integration.

## Then: real telemetry and general graph schema

- Replace fixed three-cell coordinates and the one-dimensional mobility features.
- Track stable vehicle IDs, arrivals/departures, visibility masks, missing packets and observation age.
- Define load using radio resource utilization or queue work, rather than the toy vehicle-count proxy.
- Distinguish transient bad SINR, application outage and radio-link failure.
- Preserve serving-link identity throughout a label horizon; mask censored outcomes.
- Keep train/validation/test split by original run family, including attacked copies. Add held-out scenarios.

## Then: threat model and stronger experiments

Add false velocity, false radio reports, packet dropping, and on/off attacks individually. For packet dropping, identify the attacker-controlled forwarding/transmission path. For on/off attacks, label active corrupted messages rather than every message from an attacker. Specify trusted infrastructure measurements and whether attackers can forge them.

The existing false-position injection begins at a common time and uses one offset distribution. That is useful for engineering tests but can produce an easy shortcut. Randomize onset, duration, magnitude and strategy in later experiments, and hold out attack patterns for testing. Report clean-data costs as well as robustness.

Compare reactive control, persistence/load heuristics, the exact referenced QASP method, ordinary temporal GNN and TrustGraph. The professor's QASP paper/algorithm must be supplied before claiming reproduction. The included load-aware heuristic is not QASP.

Vary vehicle density, seeds, interference and attack prevalence (0%, 5%, 10%, 20%, 30%). Report uncertainty over runs and paired policy differences. Include trust-gate ablations and shuffled-trust controls. Avoid treating overlapping windows as independent experimental replicates.

## Final validation

Measure packet delivery ratio, latency percentiles, throughput, successful/failed handovers, ping-pong rate with a stated interval, outage duration, overload duration and load fairness from actual network events. Measure inference and bridge latency. Calibrate confidence with validation data and test timeout, missing-data and out-of-distribution fallback.

Only then add a Surathkal/Mangaluru OSM scenario. PlutoSDR remains optional hardware-in-the-loop validation after the software loop is working.
