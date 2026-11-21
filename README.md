# TrustGraph-V2X

**Trust-Aware Spatio-Temporal Graph Learning for Predictive Handover and RSU Load Balancing in 5G-V2X Networks**

A handover happens when a moving vehicle switches from one serving base station to another. TrustGraph-V2X uses a trained graph model to estimate how good each radio link will be over the next two seconds and how busy each station will be one second ahead. It uses those forecasts, current measurements and safety checks to decide when to request a switch.

| Component | What it does |
| --- | --- |
| **SUMO** | Moves eight vehicles on a road map of NITK Surathkal and shows each car’s serving station |
| **Veins and OMNeT++** | Keep road traffic and the network simulation synchronized |
| **INET and Simu5G** | Simulate the network, generate radio measurements and carry out handovers |
| **TrustGraph** | Reads recent vehicle, link and load data, then reviews or proposes a handover. The model uses learned trust weights to reduce the influence of suspicious reports |

The map labels the four simulated 5G base stations **RSU1**, **RSU2**, **RSU3**, and **RSU4**. This demo covers highway traffic in both directions, a junction turn, and a car that switches twice along the highway.

## First-time setup on Windows

Use **Windows with Ubuntu 24.04 on WSL2** for the verified setup. WSL runs the Linux simulators, while Windows Python runs the trained model on the CPU. The first installation needs internet access and disk space for the simulator downloads and builds. Allow time for the one-time build. The map and trained checkpoint travel with the updated source, so running the demo requires no training.

### 1. Install the basic tools and clone the project

Install Git for Windows and 64-bit Python 3.12 with the Python launcher. Open a new **PowerShell** window and check that both commands print a version. [Git for Windows](https://git-scm.com/install/win) · [Python on Windows](https://docs.python.org/3.12/using/windows.html)

```powershell
git --version
py -3.12 --version
```

Open the Windows folder where you want the project, then run:

```powershell
git clone https://github.com/Aditya-Raj-1665/TrustGraph-V2X.git
Set-Location TrustGraph-V2X
Test-Path scripts/prepare_nitk_demo.py
Test-Path docker/assets/road.net.xml
Test-Path docker/assets/trustgraph-campus.pt
```

All three checks should print `True`. If any prints `False`, the checkout needs the revision containing the campus demo and its bundled inputs before you can follow the rest of this guide. Use a project path on a Windows drive. Spaces in the path are supported. Avoid an apostrophe in a folder name because the launcher uses shell quoting.

### 2. Install or identify Ubuntu

In PowerShell, see which distributions are already installed:

```powershell
wsl --list --verbose
```

If you already have Ubuntu 24.04 listed with `VERSION` 2, use its exact name in the remaining commands. To install it on a fresh machine, open **PowerShell as Administrator** and run:

```powershell
wsl --install -d Ubuntu-24.04
```

Restart Windows if prompted. Open Ubuntu from the Start menu once and create the Linux username and password when asked. Then run `wsl --list --verbose` again and check the **NAME** column. The launch examples below use `Ubuntu`, which is the registered name on the verified laptop. If your list shows `Ubuntu-24.04`, replace `Ubuntu` with `Ubuntu-24.04` in those commands. WSLg supplies the GUI support for the SUMO window. [Microsoft WSL commands](https://learn.microsoft.com/en-us/windows/wsl/basic-commands) · [WSL GUI support](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps)

### 3. Set up the Windows Python environment

Return to **PowerShell** in the `TrustGraph-V2X` folder. Run these commands one at a time. Stop and fix any error before continuing.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.14.0+cpu"
.\.venv\Scripts\python.exe -m pip install -e ".[dev]" "numpy==2.5.3"
.\.venv\Scripts\python.exe -c "import torch, trustgraph; print(torch.__version__)"
```

The last command checks that Python can load PyTorch and the project. You can call `.\.venv\Scripts\python.exe` directly without activating the environment. [PyTorch CPU wheels](https://pytorch.org/get-started/previous-versions/)

### 4. Install the simulator tools in Ubuntu

From the project folder in PowerShell, enter the Ubuntu shell using the distribution name you found in step 2:

```powershell
wsl -d Ubuntu
```

The commands in the next blocks run in **Ubuntu**, where the prompt typically ends in `$`. `pwd` should show the project folder starting with `/mnt/`. If you are somewhere else, `cd` to the Windows folder as seen by Ubuntu. For example, `C:\Projects\TrustGraph-V2X` becomes `/mnt/c/Projects/TrustGraph-V2X`.

```bash
pwd
ls scripts/install_network_stack.sh
sudo apt update
sudo apt install -y ca-certificates curl git python3-venv xz-utils
```

On a fresh Ubuntu installation, install single-user Nix using the following commands. If you already have a working single-user Nix profile at `~/.nix-profile/etc/profile.d/nix.sh`, skip the download and installer.

```bash
curl -fL https://releases.nixos.org/nix/nix-2.35.6/install -o ~/trustgraph-nix-install.sh
bash ~/trustgraph-nix-install.sh --no-daemon
```

If the Nix installer asks you to create `/nix`, follow the instructions it prints, then rerun it. Next load Nix and install the pinned `opp_env` and Linux SUMO tools:

```bash
source "$HOME/.nix-profile/etc/profile.d/nix.sh"
nix --version
mkdir -p "$HOME/trustgraph-tools"
python3 -m venv "$HOME/trustgraph-tools/venv"
"$HOME/trustgraph-tools/venv/bin/python" -m pip install 'opp-env==0.36.2.261110' 'eclipse-sumo==1.22.0'
"$HOME/trustgraph-tools/venv/bin/sumo" --version
```

The last command should identify SUMO 1.22.0. If you already have a different Nix installation, check the setup guide for the profile expected by this project. [Nix installation instructions](https://nix.dev/manual/nix/2.23/installation/) · [Simulator stack guide](docs/NETWORK_STACK.md)

### 5. Build the simulator stack once

Still in **Ubuntu** at the project folder, build OMNeT++, INET, and Simu5G. Wait for the prompt to return successfully before starting the Veins commands:

```bash
bash scripts/install_network_stack.sh
```

Then install and build Veins. The parentheses keep your main Ubuntu shell in the project folder:

```bash
(
  set -e
  cd "$HOME/trustgraph-simulators"
  if [ ! -d veins-5.3.1 ]; then
    curl -fL https://codeload.github.com/sommer/veins/tar.gz/refs/tags/veins-5.3.1 -o veins-5.3.1.tar.gz
    tar -xzf veins-5.3.1.tar.gz
    mv -T -n veins-veins-5.3.1 veins-5.3.1
  fi
) && bash scripts/build_veins.sh
```

The shared simulator installation lives in `~/trustgraph-simulators` inside Ubuntu. Keep it for future runs. On a memory-limited machine, prefix either build command with `TRUSTGRAPH_BUILD_JOBS=2` to use two build jobs. [Versions, build details and stack checks](docs/NETWORK_STACK.md)

### 6. Put the bundled map and model where the WSL launcher expects them

Type `exit` to return to **PowerShell**, or open PowerShell in the repository folder again. These commands create the output directories and fill in missing assets without replacing files from an existing setup:

```powershell
New-Item -ItemType Directory -Force outputs/nitk, outputs/nitk-training | Out-Null
if (!(Test-Path outputs/nitk/road.net.xml)) {
    Copy-Item -LiteralPath docker/assets/road.net.xml -Destination outputs/nitk/road.net.xml
}
if (!(Test-Path outputs/nitk-training/trustgraph-campus.pt)) {
    Copy-Item -LiteralPath docker/assets/trustgraph-campus.pt -Destination outputs/nitk-training/trustgraph-campus.pt
}
Get-FileHash outputs/nitk/road.net.xml, outputs/nitk-training/trustgraph-campus.pt
```

Compare the SHA-256 values with the bundled checksum file if you want to reproduce the exact reference run. [Expected checksums](docker/assets/SHA256SUMS) · [Asset provenance and map attribution](docker/assets/README.md)

### 7. Run the live demo

In **PowerShell**, run the model once without a window to check the setup. The commands below work on the verified laptop. On another computer, use the exact name from the **NAME** column of `wsl --list --verbose`.

```powershell
wsl -d Ubuntu -- bash scripts/run_sumo_nr.sh nitk_ml
```

Look for `"passed": true` in the verification output. Then start the live SUMO window:

```powershell
wsl -d Ubuntu -- bash scripts/run_sumo_nr.sh nitk_ml_gui
```

Watch for blue **RSU1**, orange **RSU2**, purple **RSU3**, and green **RSU4**. A car’s color and connection line change when Simu5G completes its switch. The 35-second limit is simulation time. Startup and graphics can take longer on the clock. When the final frame holds, press **Enter in the PowerShell window that launched SUMO**. Wait for the verification output and the terminal prompt to return.

After setup, repeat only the GUI launch command. To run the native Simu5G comparison, substitute `nitk_gui`. The headless and GUI ML runs write to the same result folder, so copy the results you want to keep before running again.

## Check your results

```powershell
Get-Content outputs/nitk_ml/verification.json -Raw | ConvertFrom-Json |
    Select-Object passed, verified_vehicles, model_requested, proactive
Import-Csv outputs/nitk_ml/handover-events.csv |
    Format-Table vehicle, time_s, from_gnb, to_gnb, controller, proactive
```

On the verified reference, **eight vehicles completed nine TrustGraph-requested handovers**. The model initiated three proactively and approved six candidates nominated by Simu5G. A `trustgraph` row in `controller` identifies a completed switch linked to a model request. `proactive` identifies switches where the model also chose the target before native nomination. Both controllers delivered all 13,481 application packets with 5 ms p95 delay in that lightly loaded run.

The held-out campus radio forecast had 4.36 dB mean absolute error versus 5.81 dB for persistence, which reuses the last measurement as the forecast. For one-second load, persistence had the lower error, 2.07 versus 2.16 percentage points. These results are for the documented campus runs. The separate two-cell experiments cover congestion and false-position inputs. [Exact handover times and output files](docs/SUMO_NR.md#verified-live-results) · [Campus model results](docs/CAMPUS_MODEL.md#split-selection-and-reported-numbers)

To check the Python code separately from the live simulation, run `.\.venv\Scripts\python.exe -m pytest -q` from the project folder in PowerShell.

## If something goes wrong

| What you see | What to do |
| --- | --- |
| PowerShell cannot find `.venv\Scripts\python.exe` | Confirm you are in `TrustGraph-V2X`. Use `.\.venv\Scripts\python.exe` exactly and complete step 3 if the file is missing |
| `WSL_E_DISTRO_NOT_FOUND` | Run `wsl --list --verbose` and use the exact name from the **NAME** column after `-d`. On the verified laptop, use `-d Ubuntu` |
| WSL cannot find the launch script | Open PowerShell in the `TrustGraph-V2X` folder on your Windows drive and rerun the command |
| The map or checkpoint is missing | Check step 1 for the bundled files, then repeat step 6 |
| The build prints an `Unsupported INET version` warning | The pinned setup emits this warning. Check whether the build exits successfully and the headless simulation passes verification |
| Simulation builds but the SUMO window does not appear | Check that your command ends in `nitk_ml_gui`. Check WSL2 GUI support and try the headless command to isolate the issue |
| SUMO stays on the final frame | Press Enter in the launcher terminal so it can export the results |
| The model worker fails or handover verification fails | Read the launcher output and the new run logs. The runbook tells you which file to inspect for each error |

[Detailed troubleshooting](docs/SUMO_NR.md#troubleshooting)

## Docker and long-term backup

The Docker recipe bundles the Linux simulators, the CPU model worker, and the frozen assets for `linux/amd64`. On this laptop, the stack compiled and the asset checksums passed, but the drive filled during image unpacking. The headless and Docker GUI runs still need end-to-end verification. The WSL procedure above is the verified route for the live demo. Use a drive with substantial free space if you build the Docker image. Save a tested image to separate storage for a future offline restore. [Docker setup, validation status and backup](docs/DOCKER.md)

## Technical documentation

| Guide | What you’ll find |
| --- | --- |
| [Simulator stack](docs/NETWORK_STACK.md) | Tool versions, component builds and the standalone Simu5G check |
| [NITK SUMO runbook](docs/SUMO_NR.md) | Launch modes, manual map generation, exact handover times, and output files |
| [Campus model](docs/CAMPUS_MODEL.md) | Data collection, graph features, training and held-out scores |
| [Simulator interfaces](docs/SIMULATOR_INTERFACE.md) | How data, decisions and completion events move between components |
| [Two-cell experiments](docs/NR_TRAINING_AND_CONTROL.md) | Earlier handover, congestion and false-position studies |
| [Research roadmap](docs/ROADMAP.md) and [Cleanup inventory](docs/CLEANUP.md) | Scope, limitations, retained outputs and local archives |
