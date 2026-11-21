FROM ubuntu:24.04@sha256:9a04f13b3f80ef056361e30868593b1cfd2279fe19e4081cb93a90bf56819d6a

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ca-certificates curl fontconfig fonts-dejavu-core git gzip xz-utils python3-venv \
    libgl1 libglu1-mesa libgl1-mesa-dri libxrandr2 libxcursor1 libxinerama1 libxi6 \
    libxrender1 libxxf86vm1 libxft2 xvfb x11-utils x11vnc \
    && rm -rf /var/lib/apt/lists/*
RUN if id ubuntu >/dev/null 2>&1; then userdel ubuntu; fi \
    && useradd --create-home --uid 1000 --shell /bin/bash trustgraph \
    && install -d -o trustgraph -g trustgraph /nix /app /results \
    && mkdir -p /etc/nix \
    && printf 'experimental-features = nix-command flakes\nsandbox = false\ntarball-ttl = 31536000\n' >/etc/nix/nix.conf

USER trustgraph
ENV HOME=/home/trustgraph TRUSTGRAPH_BUILD_JOBS=2
WORKDIR /app
RUN curl -fsSL https://releases.nixos.org/nix/nix-2.35.6/install -o /tmp/install-nix \
    && bash /tmp/install-nix --no-daemon \
    && rm /tmp/install-nix

RUN python3 -m venv "$HOME/trustgraph-tools/venv" \
    && "$HOME/trustgraph-tools/venv/bin/pip" install --no-cache-dir \
        'opp-env==0.36.2.261110' 'eclipse-sumo==1.22.0' \
    && python3 -m venv "$HOME/model-venv" \
    && "$HOME/model-venv/bin/pip" install --no-cache-dir 'numpy==2.5.3' \
    && "$HOME/model-venv/bin/pip" install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu 'torch==2.14.0+cpu'

ENV USER=trustgraph
COPY scripts/install_network_stack.sh scripts/
RUN bash scripts/install_network_stack.sh

COPY scripts/build_veins.sh scripts/
RUN curl -fsSL https://codeload.github.com/sommer/veins/tar.gz/refs/tags/veins-5.3.1 \
       | tar -xz -C "$HOME/trustgraph-simulators" \
    && mv "$HOME/trustgraph-simulators/veins-veins-5.3.1" "$HOME/trustgraph-simulators/veins-5.3.1" \
    && bash scripts/build_veins.sh

COPY scripts/ scripts/
COPY simulations/veins/ simulations/veins/
COPY trustgraph/ trustgraph/
COPY docker/assets/ docker/assets/
COPY docker/entrypoint.sh docker/entrypoint.sh
RUN cd docker/assets && sha256sum -c SHA256SUMS

ENV TRUSTGRAPH_WORKER_PYTHON=/home/trustgraph/model-venv/bin/python \
    TRUSTGRAPH_OUTPUT_ROOT=/results \
    TRUSTGRAPH_CAMPUS_MAP=/app/docker/assets/road.net.xml \
    TRUSTGRAPH_CAMPUS_CHECKPOINT=/app/docker/assets/trustgraph-campus.pt \
    PYTHONDONTWRITEBYTECODE=1

ENTRYPOINT ["bash", "/app/docker/entrypoint.sh"]
CMD ["nitk_ml"]
