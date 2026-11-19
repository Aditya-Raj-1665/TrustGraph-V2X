#!/usr/bin/env bash
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ${1:-} != --inside ]]; then
    mode=${1:-baseline}
    case "$mode" in
        baseline|batch|pilot|closed|stress_probe|stress|adaptive_probe|adaptive_batch|adaptive_control|adaptive_early|adaptive_early_rule|adaptive_final) ;;
        *) exit 2 ;;
    esac
    source "$HOME/.nix-profile/etc/profile.d/nix.sh"
    export PATH="$HOME/trustgraph-tools/venv/bin:$PATH"
    cd "$HOME/trustgraph-simulators"
    exec opp_env run -w "$HOME/trustgraph-simulators" --no-build --build-modes=release \
        simu5g-1.8.1 inet-4.7.0 omnetpp-6.4.0 -c "bash '$project/scripts/run_sumo_nr.sh' --inside $mode"
fi

workspace=$(dirname -- "$SIMU5G_ROOT")
veins="$workspace/veins-5.3.1"
veins_inet="$veins/subprojects/veins_inet"
export PATH="$(dirname -- "$workspace")/trustgraph-tools/venv/bin:$PATH"
output="$project/outputs/sumo-nr"
mkdir -p "$output"
work=$(mktemp -d "$workspace/sumo-nr.XXXXXX")
echo "Simulation work directory: $work"
cp "$project"/simulations/veins/* "$work/"
cp "$SIMU5G_ROOT/simulations/nr/standalone_multicell/omnetpp.ini" "$work/upstream.ini"
cp "$SIMU5G_ROOT/simulations/nr/standalone_multicell/demo.xml" "$work/"
cd "$work"

netconvert --node-files road.nod.xml --edge-files road.edg.xml --output-file road.net.xml
opp_makemake --make-so -f -o mobility_probe \
    -I"$INET_ROOT/src" -I"$SIMU5G_ROOT/src" -I"$veins/src" -I"$veins_inet/src" \
    -L"$SIMU5G_ROOT/src" -lsimu5g -L"$veins_inet/src" -lveins_inet
make -j4 MODE=release
ned="$work:$SIMU5G_ROOT/simulations:$SIMU5G_ROOT/src:$INET_ROOT/src:$veins/src/veins:$veins_inet/src/veins_inet"
simulate() {
local log=${2:-run.log}
if ! opp_run -u Cmdenv -n "$ned" \
    -x "simu5g.simulations.lte.cars;simu5g.simulations.nr.cars" \
    -l "$INET_ROOT/src/INET" -l "$veins/src/veins" -l "$veins_inet/src/veins_inet" \
    -l "$SIMU5G_ROOT/src/simu5g" -l "$work/mobility_probe" \
    -f omnetpp.ini -c "$1" -r 0 > "$log" 2>&1; then
    tail -n 40 "$log" >&2
    exit 1
fi
}
if [[ ${2:-baseline} == pilot || ${2:-baseline} == closed || ${2:-baseline} == stress* || ${2:-baseline} == adaptive_* ]]; then
    root="$project/outputs/nr-control"
    mkdir -p "$root"
    closed=$(mktemp -d "$root/suite.XXXXXX")
    echo "Controller results: $closed"
    trials=(09 10 11)
    conditions=(clean false_position)
    policies=(native fixed_rules graph_without_trust trustgraph)
    options=()
    if [[ $2 == stress* ]]; then
        options=(--stress)
        trials=(20 21 22)
        conditions=(congested)
        policies=(native fixed_rules trustgraph)
        if [[ $2 == stress_probe ]]; then
            trials=(20)
            conditions=(calm congested)
            policies=(native)
        fi
    fi
    if [[ $2 == adaptive_* ]]; then
        conditions=(clean)
        policies=(native)
        if [[ $2 == adaptive_probe ]]; then
            options=(--adaptive-probe)
            trials=(30 31 32)
        else
            options=(--adaptive-batch)
            trials=(40 41 42 43 44 45 46 47 48 49 50 51)
            if [[ $2 == adaptive_control || $2 == adaptive_early* || $2 == adaptive_final ]]; then
                trials=(49 50 51)
                conditions=(clean false_position)
                policies=(native fixed_rules trustgraph)
            fi
            if [[ $2 == adaptive_early ]]; then
                policies=(trustgraph_early)
            fi
            if [[ $2 == adaptive_early_rule ]]; then
                policies=(fixed_rules_early)
            fi
            if [[ $2 == adaptive_final ]]; then
                options=(--adaptive-final)
                trials=(60 61 62 63 64 65)
                policies+=(fixed_rules_early trustgraph_early)
            fi
        fi
    fi
    python3 "$project/scripts/prepare_nr_trials.py" "$work" "${options[@]}"
    run_variant() (
                local trial=$1 condition=$2 policy=$3
                variant=$(mktemp -d "$work/closed.XXXXXX")
                cp "$work/trial-$trial/"* "$variant/"
                result="$closed/trial-$trial-$condition-$policy"
                mkdir "$result"
                cp "$variant/trial.json" "$result/"
                cd "$variant"
                if [[ "$condition" == calm ]]; then
                    sed -i 's/\.samplingTime = 0.002s/.samplingTime = 0.1s/' omnetpp.ini
                    python3 -c 'import json; from pathlib import Path; p=Path("trial.json"); d=json.loads(p.read_text()); d["offered_packet_interval_s"]=0.1; p.write_text(json.dumps(d))'
                    cp trial.json "$result/"
                fi
                ln -s "$result" bridge
                netconvert --node-files "$work/road.nod.xml" --edge-files road.edg.xml --output-file road.net.xml
                if [[ "$policy" != native ]]; then
                    cat >> omnetpp.ini <<'INI'
cmdenv-autoflush = true
*.policy.enabled = true
*.policy.cmdenv-log-level = info
*.car[*].cellularNic.rrc.nrConnectionControl.typename = "PolicyConnectionControl"
INI
                fi
                if [[ "$policy" == *_early ]]; then
                    echo '*.policy.earlyOffload = true' >> omnetpp.ini
                fi
                echo "Running $(basename "$result")"
                simulate Trial "$result/run.log"
                cp handover.vec handover.sca sumo-fcd.xml "$result/"
                touch "$result/finished"
    )
    if [[ $2 == adaptive_probe || $2 == adaptive_batch ]]; then
        pids=()
        for trial in "${trials[@]}"; do
            run_variant "$trial" clean native &
            pids+=("$!")
            if [[ ${#pids[@]} == 3 || $trial == "${trials[-1]}" ]]; then
                failed=0
                for pid in "${pids[@]}"; do
                    wait "$pid" || failed=1
                done
                [[ $failed == 0 ]] || exit 1
                pids=()
            fi
        done
        touch "$closed/finished"
        exit 0
    fi
    for trial in "${trials[@]}"; do
        for condition in "${conditions[@]}"; do
            pids=()
            for policy in "${policies[@]}"; do
                if [[ $2 == pilot && "$trial-$condition-$policy" != 09-clean-trustgraph ]]; then
                    continue
                fi
                if [[ $2 == stress || $2 == adaptive_control || $2 == adaptive_final ]]; then
                    run_variant "$trial" "$condition" "$policy" &
                    pids+=("$!")
                else
                    run_variant "$trial" "$condition" "$policy"
                fi
            done
            failed=0
            for pid in "${pids[@]}"; do
                wait "$pid" || failed=1
            done
            [[ $failed == 0 ]] || exit 1
        done
    done
    touch "$closed/finished"
    exit 0
fi
if [[ ${2:-baseline} == batch ]]; then
    batch=$(mktemp -d "$project/outputs/nr-trials.XXXXXX")
    echo "Batch results: $batch"
    python3 "$project/scripts/prepare_nr_trials.py" "$work"
    for scenario in "$work"/trial-*; do
        cd "$scenario"
        echo "Running $(basename "$scenario")"
        netconvert --node-files "$work/road.nod.xml" --edge-files road.edg.xml --output-file road.net.xml
        simulate Trial
        mkdir "$batch/$(basename "$scenario")"
        cp handover.vec handover.sca run.log sumo-fcd.xml trial.json "$batch/$(basename "$scenario")/"
    done
    exit 0
fi
simulate TrustGraphVeins
python3 "$project/scripts/verify_nr_handover.py" "$work" --node 'car[0]'
python3 "$project/scripts/verify_sumo_positions.py" "$work"
cp run.log handover.sca handover.vec sumo-fcd.xml road.net.xml \
    verification.json positions.json "$output/"
