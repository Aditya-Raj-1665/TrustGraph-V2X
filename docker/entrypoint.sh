#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
    nitk|nitk_ml|nitk_gui|nitk_ml_gui|nitk_collect) ;;
    *) echo 'Choose nitk_ml, nitk_ml_gui, nitk, nitk_gui or nitk_collect.' >&2; exit 2 ;;
esac

if [[ $1 == *_gui ]]; then
    export DISPLAY=:99
    Xvfb "$DISPLAY" -screen 0 1280x900x24 -nolisten tcp &
    display_pid=$!
    trap 'kill "$display_pid" 2>/dev/null || true' EXIT
    for ((attempt=0; attempt<50; ++attempt)); do
        if xdpyinfo >/dev/null 2>&1; then break; fi
        sleep 0.1
    done
    xdpyinfo >/dev/null
    x11vnc -display "$DISPLAY" -rfbport 5900 -listen 0.0.0.0 -forever -shared -nopw > /tmp/trustgraph-vnc.log 2>&1 &
    echo 'Connect a VNC viewer to the localhost port published by Docker.'
    bash scripts/run_sumo_nr.sh "$1"
else
    exec bash scripts/run_sumo_nr.sh "$1"
fi
