FROM ghcr.io/openclaw/openclaw:latest

USER root

# Install system deps (cached unless base image changes)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends python3-pip

# Install Python deps (only re-runs when requirements.txt changes)
COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install --break-system-packages -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

USER node
