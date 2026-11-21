#!/usr/bin/env bash
# Run inside Ubuntu WSL. Pinned upstream-compatible simulator stack.
set -euo pipefail
source "$HOME/.nix-profile/etc/profile.d/nix.sh"
export PATH="$HOME/trustgraph-tools/venv/bin:$PATH"
printf -v NIX_CONFIG 'cores = %s\nmax-jobs = 1' "${TRUSTGRAPH_BUILD_JOBS:-4}"
export NIX_CONFIG
mkdir -p "$HOME/trustgraph-simulators"
cd "$HOME/trustgraph-simulators"
if [ ! -d .opp_env_workspace ]; then
    opp_env init --force
fi
opp_env install --no-pause --build-modes=release --smoke-test simu5g-1.8.1 inet-4.7.0 omnetpp-6.4.0 2>&1 | tee install.log
