#!/bin/bash
set -euo pipefail

cd /comfyui
if [ -d /runpod-volume/models ]; then
    cp /opt/runpod/runpod_model_paths.yaml /comfyui/extra_model_paths.yaml
fi

python main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch &
echo $! > /tmp/comfyui.pid

exec python -u /opt/runpod/handler.py
