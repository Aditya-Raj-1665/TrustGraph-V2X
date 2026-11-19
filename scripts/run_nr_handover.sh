#!/usr/bin/env bash
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [ "${1:-}" != "--inside" ]; then
    source "$HOME/.nix-profile/etc/profile.d/nix.sh"
    export PATH="$HOME/trustgraph-tools/venv/bin:$PATH"
    exec opp_env run -w "$HOME/trustgraph-simulators" --no-build --build-modes=release \
        simu5g-1.8.1 inet-4.7.0 omnetpp-6.4.0 \
        -c "bash '$project/scripts/run_nr_handover.sh' --inside"
fi
cd "$SIMU5G_ROOT/simulations/nr/standalone_multicell"
cp "$project/configs/nr_handover.ini" trustgraph.ini
for config in TrustGraphHandover TrustGraphStationary; do
    output="$project/outputs/nr-handover/$config"
    mkdir -p "$output"
    if ! simu5g -u Cmdenv -f trustgraph.ini -c "$config" -r 0 --result-dir="$output" > "$output/run.log" 2>&1; then
        tail -n 30 "$output/run.log" >&2
        exit 1
    fi
    if [ "$config" = TrustGraphStationary ]; then
        python3 "$project/scripts/verify_nr_handover.py" "$output" --stationary
    else
        python3 "$project/scripts/verify_nr_handover.py" "$output"
    fi
done
