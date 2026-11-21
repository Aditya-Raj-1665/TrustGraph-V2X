# Project cleanup inventory

This inventory records what was kept and what was removed after the NITK demo. Archived sizes refer to the original loose files.

| Mark | Paths | Reason and action |
|---|---|---|
| Keep at current paths | `outputs/nitk/`, `outputs/nitk-training/`, `outputs/nitk_ml/` | The launcher copies the native reference map and loads the trained campus checkpoint. Preserve the matched native and model results, verification, screenshots and event logs. |
| Keep with source | `docker/assets/road.net.xml`, `docker/assets/trustgraph-campus.pt`, `docker/assets/SHA256SUMS` | Frozen map and model for new checkouts. These are the explicit Git exceptions for the campus inputs. |
| Keep for reproduction | `outputs/nitk_collect/`, `outputs/nr-congestion-mae/` | The 12 campus traces and earlier training checkpoint support retraining. |
| Keep installed | `.venv/` (1,532 MiB), local package metadata, WSL simulator installation | The launcher starts the local Windows Python worker. Reinstalling these dependencies would cost substantially more than keeping them. The WSL installation is outside this folder. |
| Keep source | `trustgraph/`, `scripts/`, `configs/`, `simulations/`, `tests/`, package files and Git metadata | Includes campus integration, older comparison policies and tests. |
| Keep cited results | Nine cited suites in `outputs/nr-control/`, including `suite.RMgcbb`; `outputs/nr-handover/`, `outputs/sumo-nr/`, `outputs/nr-trials.*/`, `outputs/nr-training/`, `outputs/nr-congestion-training/` | Prior experiments have separate provenance. Keep their raw inputs and results available at their existing paths. |
| Keep earlier experiments | `outputs/corridor/`, `outputs/intersection/`, `outputs/sumo/`, `outputs/demo/`, prediction and validation JSON | Earlier simulator and model evidence. |
| Archive, then remove loose copies | Under `outputs/nr-control/`, the four uncited suites `suite.APFKkQ`, `suite.mpp80K`, `suite.tUydz4`, `suite.UZP743` (about 607 MiB combined) | Earlier runs may contain unique simulator events. Preserve every file in the local archive. |
| Archive, then remove loose copies | Under `outputs/`, `manual-test/`, `visual-demo/`, `midsem-live/`, `final-live/` (about 7 MiB combined) | Their mobility CSV and metadata match the retained `sumo/` run byte for byte. The generated network XML differs, so retain the original files in the archive. |
| Removed | Midsemester PDFs, HTML slides and report, browser replay, launchers, presentation guide, ZIP, build code and browser QA files | The live SUMO simulation is the project's showcase. |
| Archive stopped workers | Six `outputs/nitk_ml/bridge.*` directories | Preserve raw worker logs and requests in `outputs/cleanup-2026-11-21-bridges.zip`. Keep the exported policy log, checkpoint identity and simulator evidence at their usual paths. |
| Remove generated files | Repository Python bytecode, pytest cache and cleanup test scratch data | Python regenerates these as needed. |
| Updated | `README.md` and technical guides | The README walks through a fresh clone. The guides cover the verified WSL demo, research experiments and Docker validation status. |

The two local archives contain paths relative to the repository root. On Windows, extract into an empty destination to inspect the archives alongside newer runs. From the repository root:

```powershell
Expand-Archive -LiteralPath outputs/cleanup-2026-11-20.zip -DestinationPath outputs/restored-experiments
Expand-Archive -LiteralPath outputs/cleanup-2026-11-21-bridges.zip -DestinationPath outputs/restored-bridges
```

Git ignores generated results, archives, environments, and the working map and checkpoint under `outputs/`. The bundled inputs under `docker/assets/` let a fresh checkout of the updated revision run the verified WSL demo after installing the simulator stack. [First-time setup](../README.md#first-time-setup-on-windows)
