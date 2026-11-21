# Windows and WSL simulator setup

## Pinned stack

- Ubuntu 24.04 under WSL2
- Single-user Nix 2.35.6 in the verified Ubuntu environment
- opp-env 0.36.2.261110, installed in `~/trustgraph-tools/venv`
- OMNeT++ 6.4.0
- INET 4.7.0
- Simu5G 1.8.1
- Veins 5.3.1, including its `veins_inet` subproject
- Eclipse SUMO 1.22.0 inside WSL, including `sumo-gui` and `netconvert`
- Windows Python 3.12.5 with CPU PyTorch 2.14.0 in the verified campus environment

The version combination is declared compatible by the upstream opp_env database
and [Simu5G release notes](https://simu5g.org/neddoc/whatsnew.html).
The official [installation guide](https://simu5g.org/install) recommends opp_env.
The simulator workspace is `~/trustgraph-simulators` inside Ubuntu, outside
Dropbox and the Git repository. Nix dependencies are stored in `/nix`.

## 1. Windows and Ubuntu

Use the existing Ubuntu 24.04 WSL2 distribution if it is already configured. In PowerShell, `wsl --list --verbose` shows the exact distribution name and WSL version to use. For installation and the first Ubuntu sign-in, follow the README. [Install or identify Ubuntu](../README.md#2-install-or-identify-ubuntu)

Keep the repository on a Windows drive because the campus launcher invokes a Windows Python executable from WSL. Use Windows PowerShell in the repository root for Python setup and training. The Ubuntu shell sees the same drive under `/mnt/c` for C:. For example, `C:\Projects\TrustGraph-V2X` becomes `/mnt/c/Projects/TrustGraph-V2X`. Quote paths with spaces. Use a checkout path without apostrophes because the launcher quotes its inner script path using shell single quotes.

The Windows environment supplies CPU model inference, training and tests. The optional `sumo` extra installs a separate Windows SUMO for standalone mobility experiments. The campus GUI uses the WSL SUMO installation below. [CPU environment setup](../README.md#3-set-up-the-windows-python-environment) · [Verified Windows dependency versions](../requirements-lock.txt)

## 2. Nix and simulator tools

The simulator scripts source the single-user profile at `~/.nix-profile/etc/profile.d/nix.sh`. Use the README's pinned setup commands on a fresh installation. If you already have another Nix profile, check its location before running the launcher. The commands below check the expected setup. [Install the simulator tools](../README.md#4-install-the-simulator-tools-in-ubuntu)

```bash
source "$HOME/.nix-profile/etc/profile.d/nix.sh"
nix --version
"$HOME/trustgraph-tools/venv/bin/python" -m pip show opp-env eclipse-sumo
"$HOME/trustgraph-tools/venv/bin/sumo" --version
```

The version above is the verified opp_env release. If a package index cannot provide it, check the upstream install instructions and record which version you use. A changed opp_env database may select a different dependency build even when the launcher requests the same simulator release. [opp_env installation](https://github.com/omnetpp/opp_env/blob/main/INSTALL.md)

## 3. Build OMNeT++, INET and Simu5G

From the repository root in Ubuntu:

```bash
bash scripts/install_network_stack.sh
```

This builds release binaries with four compilation cores by default and runs upstream smoke
tests. Installation logs remain at `~/trustgraph-simulators/install.log`.
Initial installation downloads substantial dependencies. Check Windows free space and `df -h "$HOME" /nix` in Ubuntu because the WSL virtual disk can grow. Later launches use `opp_env run --no-build` for the installed stack and still compile the project's local adapter in a new run directory.

## 4. Install and build Veins

The README gives the commands to place the Veins 5.3.1 source beside the simulator projects and run `bash scripts/build_veins.sh`. The script builds Veins and `veins_inet` against INET 4.7.0. It removes two unused includes of an old INET UDP header in the local Veins source before configuring the subproject. Both build steps use four concurrent make jobs by default. Set `TRUSTGRAPH_BUILD_JOBS` to a smaller number when memory is limited. Veins launches SUMO through TraCI. [Build commands](../README.md#5-build-the-simulator-stack-once) · [Veins release](https://github.com/sommer/veins/releases/tag/veins-5.3.1)

Veins 5.3.1 can print an `Unsupported INET version` compiler warning for INET 4.7.0. The pinned campus build emits this warning and has passed the simulator checks. Check the build exit status and headless verification result.

Next, copy the bundled road map and model into the WSL launcher's input paths. Run `nitk_ml` for the headless test and `nitk_ml_gui` for the live demo. The standalone network acceptance check below can isolate Simu5G setup failures. [Copy the bundled assets](../README.md#6-put-the-bundled-map-and-model-where-the-wsl-launcher-expects-them) · [Campus launch and verification](SUMO_NR.md)

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
The [campus co-simulation guide](SUMO_NR.md) builds on this baseline with SUMO mobility and live model decisions.
