# Midsemester demonstration guide

## Open the prepared package

Double-click **Open-Midsem.cmd** in the TrustGraph-V2X folder. For slides, double-click **Open-Slides.cmd**. These launchers locate the project themselves, so your current PowerShell folder does not matter.

You can also open `midsem/index.html`, `midsem/slides.html` and `midsem/report.html` directly. Keep the entire `midsem` folder together when moving the presentation to another computer. There are no remote JavaScript, font or data dependencies. The browser replay uses already recorded model outputs and needs no running Python service.

The portable ZIP contains the same offline package: extract it first and double-click `OPEN_DEMO.cmd` or `index.html`. Prepared slide and report PDFs are included. The report also has a Print / Save as PDF button, and slides support landscape printing. Browser-ready slides are the editable presentation format; a native PowerPoint file is not included.

## An eight-minute walkthrough

1. **Explain the goal, 1 minute.** We want to predict deteriorating serving links and future cell load while reducing the influence of false vehicle reports. State that the system is a midsemester prototype.
2. **Show SUMO mobility, 1 minute.** Open the SUMO mobility tab and press Play traffic. Explain moving and stopped vehicles. The source is the actual 20-vehicle SUMO run with 20,509 telemetry rows. Radio links and traffic-light states are not part of this CSV replay.
3. **Introduce the network view, 1 minute.** Return to Network replay. It is a separate synthetic straight-road experiment with three cells. Select the clean scenario and show reported position, serving SINR and predicted load. Do not describe this view as integrated SUMO and Simu5G.
4. **Show the attack, 2 minutes.** Select False-position attack, then Before attack. The default selected vehicle is the first attacker by identity, not one selected for model success. Press Play or use the right arrow. At 1.5 seconds its report changes. Point to the dashed reported position, the true-position overlay and the learned attack score. Toggle Ground-truth overlay off to explain what the model observes. The model may miss the attack or raise false alarms; show the actual value.
5. **Show the mechanism and decision, 1 minute.** Explain that the trust score multiplies outgoing graph messages. The gate-disabled number uses the same weights, which isolates the gating mechanism. Click Next handover. Read whether the action used model scoring or conventional fallback. The next frame shows the new serving cell. Do not claim every move is AI-driven or caused by the attack.
6. **Show initial evidence, 1 minute.** Open Initial results. Explain the run split and compare neural models with fixed rules. State that the present results do not show a consistent TrustGraph advantage. Delivery proxy is not measured packet delivery ratio.
7. **Close with scope, 1 minute.** Open Project scope or return to the final slides. The next acceptance criterion is a model command causing a completed handover in integrated SUMO and Simu5G, with event logs.

## Controls

- Network replay: Space plays or pauses, left/right arrows step by 100 ms, slider seeks. You can click a car or select its ID.
- Before attack seeks to 1.2 s. Attack starts seeks to 1.5 s in the attacked scenario.
- Next handover finds the next recorded move and selects its vehicle. The displayed command applies at that step; the following snapshot reflects the changed serving cell.
- The truth overlay is evaluation-only. It never enters model inference.
- Slides: right/left arrows or Page Down/Page Up navigate. N toggles speaker notes. Full screen is optional. Notes are hidden when printing.

## Original SUMO window

From the TrustGraph-V2X folder:

```powershell
.\.venv\Scripts\python.exe -m trustgraph sumo --gui --output outputs/midsem-live
```

Use the browser mobility recording if SUMO cannot launch on the presentation computer. It is a recording of the actual exported run, not an invented animation.

## Rebuilding and checking

```powershell
.\.venv\Scripts\python.exe -m trustgraph midsem --output midsem
.\.venv\Scripts\python.exe -m pytest -q
```

The exporter reloads the original checkpoint, runs the clean and attacked environments with seed 1001 and records observations, predictions and actions. It stores hashes of the checkpoint and SUMO source CSV in `midsem/evidence.json`. Existing model weights and experiment results are not retrained or changed by this command.

## Likely questions and concise answers

**Is this a completed 5G simulation?** No. SUMO mobility is real simulator output, while the current network-learning loop uses a simplified Python environment. Real Veins and Simu5G integration is next.

**What makes the model trust-aware?** A local GRU estimates active telemetry corruption. One minus that score scales the sender's graph message before aggregation. Ground-truth attack labels supervise training but are excluded from inputs.

**Why a graph?** Vehicle and access-cell relationships influence the available information. Graph aggregation offers a way to combine that information. The current experiments still need to show when it improves on simpler models.

**Why a GRU?** The task depends on recent motion and radio changes, so the model uses a short temporal sequence rather than a single snapshot.

**What is the novelty?** The proposed contribution is trust weighting inside the predictive graph model. Novelty and practical benefit are still under investigation; do not claim literature-wide novelty based solely on this prototype.

**Is it better than the baseline?** Not consistently in the current small experiment. We report both models and simple baselines, and will test broader conditions with real network telemetry.

**Why are some decisions fallback?** The controller applies a certainty threshold, dwell time and eligibility rules. The certainty score is a heuristic, not calibrated confidence. Fallback is part of the implemented controller.

**Can it handle arbitrary maps or vehicles entering and leaving?** The current neural environment has a fixed straight road, three cells and stable identities within a window. Dynamic identities, 2D motion and real radio measurements must be implemented for the integrated simulator.

**Will the full project be complete next week?** The target is to implement the simulator integration and close the control loop. The build and compatibility checks determine the achievable schedule. Show the stage acceptance criteria rather than guarantee an unverified completion date.

## Before presenting

Open the demo and slides once on the presentation computer. Confirm that data.js stayed alongside the HTML files. Fill in your team, department and guide details in the report cover before printing. Keep a copy of the PDF handouts if available. Do not claim that the synthetic network replay shows actual 5G packet exchange.
