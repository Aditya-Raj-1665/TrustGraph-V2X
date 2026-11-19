# NR simulator installation and handover acceptance

## Pinned stack

- Ubuntu 24.04 under WSL2
- opp-env 0.36.2.261110, installed in `~/trustgraph-tools/venv`
- OMNeT++ 6.4.0
- INET 4.7.0
- Simu5G 1.8.1

The version combination is declared compatible by the upstream opp_env database
and [Simu5G release notes](https://simu5g.org/neddoc/whatsnew.html).
The official [installation guide](https://simu5g.org/install) recommends opp_env.
The simulator workspace is `~/trustgraph-simulators` inside Ubuntu, outside
Dropbox and the Git repository. Nix dependencies are stored in `/nix`.

## Build

Requires an installed Nix single-user environment and the isolated opp_env
installation above. From the project directory in Ubuntu:

```bash
bash scripts/install_network_stack.sh
```

This builds release binaries with four compilation cores and runs upstream smoke
tests. Installation logs remain at `~/trustgraph-simulators/install.log`.
Initial installation downloads substantial dependencies; check Windows free
space as well as Linux free space because the WSL virtual disk grows on C:.

## Acceptance run

After all builds and smoke tests pass:

```bash
bash scripts/run_nr_handover.sh
```

The configuration extends the upstream `standalone_multicell` CBR-DL example:
two gNBs at x=250 m and x=750 m, one NR UE moving east at 15 m/s, downlink
traffic, 35 simulated seconds and seed 1001. A second run holds the UE stationary.
The runner writes into `outputs/nr-handover/` (excluded from Git).

Acceptance requires the moving UE's NR `servingCell` vector to change from
cell 1 to cell 2, the stationary control to retain its cell, and both runs to
reach the simulation time limit. Both runs must receive application packets;
the moving run must receive packets before and after its cell transition.
Simu5G emits the serving-cell signal after updating its
Binder, PHY, MAC and feedback-generator handover state in
`ConnectionControlUe::doHandover()`. An initial attachment alone does not pass.

## Verified result

On 19 November 2026, OMNeT++, INET and Simu5G passed their upstream smoke
tests. The moving vehicle started on gNB 1 and completed a handover to gNB 2
at 16.05001 simulated seconds. It received 1,741 application packets, including
packets before and after the transition. The stationary vehicle stayed on gNB 1
and also received 1,741 packets. Both runs reached 35 simulated seconds.

Each run directory contains `verification.json`, `run.log`, and the original
OMNeT++ scalar and vector files. The moving run log records the completion in
`ConnectionControlUe::doHandover()`.

## Scope

This is a conventional NR handover acceptance test, using INET linear mobility.
It does not connect SUMO/Veins or the learned controller. Those integrations
follow once the network stack and this baseline run are verified.
