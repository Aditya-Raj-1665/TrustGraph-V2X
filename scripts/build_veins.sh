#!/usr/bin/env bash
set -euo pipefail
workspace="$HOME/trustgraph-simulators"
if [[ ${1:-} != --inside ]]; then
    source "$HOME/.nix-profile/etc/profile.d/nix.sh"
    export PATH="$HOME/trustgraph-tools/venv/bin:$PATH"
    script=$(realpath -- "${BASH_SOURCE[0]}")
    cd "$workspace"
    exec opp_env run -w "$workspace" --no-build --build-modes=release \
        simu5g-1.8.1 inet-4.7.0 omnetpp-6.4.0 -c "bash '$script' --inside"
fi
workspace=$(dirname -- "$SIMU5G_ROOT")
cd "$workspace/veins-5.3.1"
./configure
make -j4 MODE=release
cd subprojects/veins_inet
# INET 4.7 removed this header. These applications use UdpSocket and
# packet tags, so the old header is unnecessary.
for source in VeinsInetApplicationBase.cc VeinsInetSampleApplication.cc; do
    sed -i '/^#include .*\/UdpControlInfo_m\.h"$/d' "src/veins_inet/$source"
done
./configure --with-inet="$workspace/inet-4.7.0"
make -j4 MODE=release
