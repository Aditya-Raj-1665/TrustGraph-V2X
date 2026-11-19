#!/usr/bin/env bash
set -euo pipefail
scripts=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bash "$scripts/install_network_stack.sh"
bash "$scripts/run_nr_handover.sh"
