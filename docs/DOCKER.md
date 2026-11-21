# Docker and long-term reproduction

The Docker recipe packages SUMO, Veins, OMNeT++, INET, Simu5G, a Linux CPU model worker, and the frozen campus map and checkpoint. It targets `linux/amd64`. It uses the Linux engine in Docker Desktop on Windows and carries its own Python tools.

**Validation status.** The simulator libraries compiled, both bundled asset hashes matched, and Docker exported the image layers. Windows ran out of disk space during unpacking, before the container simulation started. The offline run, GUI run and save/load cycle remain unverified. For a live demonstration with the verified setup, use the [Windows and WSL guide](../README.md#first-time-setup-on-windows).

## Build and verify

Check free space on the drive that holds Docker's data **before** starting. The attempted Windows build started with roughly 30 GiB free and still ran out during image unpacking. The initial build needs room for downloaded dependencies, compiled files, build cache and the unpacked image at the same time. Moving the checkout alone leaves Docker's data on its original drive.

From the repository root in PowerShell, with Docker Desktop running in Linux container mode:

```powershell
docker compose build headless
docker compose run --rm --no-deps --pull never headless
```

The headless service has networking disabled. It uses the same model, scenario and verification as the GUI. On success it creates `outputs/docker/nitk_ml/verification.json`, `handover-events.csv`, `policy.jsonl` and the raw simulator evidence. On Linux, make the bind-mounted output directory writable by the container user (UID 1000).

```powershell
$run = Get-Content outputs/docker/nitk_ml/verification.json -Raw | ConvertFrom-Json
$run | Select-Object passed, verified_vehicles, model_requested, proactive
```

Compare the result with the verified campus reference of eight cars, nine model-requested completions and three proactive selections. [NITK runbook](SUMO_NR.md#verified-live-results)

## Show the live SUMO window

From PowerShell:

```powershell
docker compose run --rm --no-deps --pull never --service-ports gui
```

Open a VNC viewer on the same machine and connect to `127.0.0.1`, port `5900`. The viewer displays the live `sumo-gui` process. The port is published to Windows loopback only, and the viewer session has no password. Keep that binding local. If the port is already occupied, change the host-side port in `compose.yaml` and use that port in the viewer.

The live run holds its final frame after 35 simulated seconds. Press **Enter** in the PowerShell window that launched the container to finish and export the evidence. GUI and headless results share the same destination. Save any run you want to compare before repeating it.

## Preserve the actual image

Keep the Docker recipe and frozen inputs together with the source revision. A source clone can build while the referenced packages and caches are available. After validating the offline and GUI runs, save the tested image and its checksum to separate backup storage. The image archive can be several gigabytes. Run the save commands on a backup volume with enough space.

```powershell
docker image save -o trustgraph-v2x-campus-1.tar trustgraph-v2x:campus-1
Get-FileHash trustgraph-v2x-campus-1.tar -Algorithm SHA256
```

On the future machine, clone the same source revision, verify the archive checksum against the saved value, then load and run it:

```powershell
docker image load -i trustgraph-v2x-campus-1.tar
docker compose run --rm --no-deps --pull never headless
docker compose run --rm --no-deps --pull never --service-ports gui
```

The archive contains the packaged Linux dependencies, source, model and map. Save it outside ordinary Git. Record the source revision, image tag and archive SHA-256 together. The base image uses a digest and the main simulator and model versions are fixed. Ubuntu package indexes and some transitive build dependencies can still change. An archived tested image avoids re-resolving them. [Docker image save](https://docs.docker.com/reference/cli/docker/image/save/)

### Bundled assets and data

Docker builds use the two files in `docker/assets/`, with SHA-256 verification. Docker excludes local results, training traces, credentials, the Windows virtual environment and Git metadata from its build context. The image does not include the separate warm-start checkpoint or held-out training logs. `nitk_collect` can collect fresh simulator data with the bundled map. [Frozen inputs and map attribution](../docker/assets/README.md) · [Model training](CAMPUS_MODEL.md)

To train a separate candidate in Docker, collect fresh traces and write the result to the mounted output directory:

```powershell
docker compose run --rm --no-deps --pull never headless nitk_collect
docker compose run --rm --no-deps --pull never --entrypoint /home/trustgraph/model-venv/bin/python headless -m trustgraph.nr_campus train /results/nitk_collect /results/nitk-training-candidate
```

This trains from a new initialization. To reproduce the original warm start, put the earlier checkpoint in `outputs/docker/` and append `--warm-start /results/<checkpoint-file>` to the training command. Evaluate a candidate by overriding the checkpoint path for one headless run:

```powershell
docker compose run --rm --no-deps --pull never -e TRUSTGRAPH_CAMPUS_CHECKPOINT=/results/nitk-training-candidate/trustgraph-campus.pt headless
```

Candidate runs write to the same result paths as the bundled model. Preserve earlier results before comparing.
