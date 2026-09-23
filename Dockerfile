# RunPod serverless worker for this ComfyUI tree.
# Models are not baked in. Attach a network volume and put them under
# /runpod-volume/models (checkpoints, loras, vae, clip, unet, ...).
#
# Build:  docker build --platform linux/amd64 -t comfyui-runpod .
# Deploy the image as a RunPod Serverless endpoint (GPU). The container
# listens for jobs; it does not publish the ComfyUI UI.

FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_PREFER_BINARY=1 \
    PIP_NO_INPUT=1 \
    PYTHONUNBUFFERED=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    DO_NOT_TRACK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        python3-dev \
        python3-pip \
        build-essential \
        git \
        wget \
        ca-certificates \
        libgl1 \
        libglib2.0-0 \
        ffmpeg \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

RUN wget -qO- https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.local/bin/uv /usr/local/bin/uv \
    && uv venv /opt/venv

ENV PATH="/opt/venv/bin:${PATH}"

# cu128 wheels run on the CUDA 12.8 hosts RunPod schedules. Install them
# before requirements.txt so the bare `torch` pin does not pull a cu13 build.
RUN uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

WORKDIR /comfyui
COPY requirements.txt .
RUN uv pip install -r requirements.txt \
    && uv pip install runpod requests

COPY . /comfyui
COPY docker/runpod/handler.py docker/runpod/start.sh docker/runpod/runpod_model_paths.yaml /opt/runpod/
RUN chmod +x /opt/runpod/start.sh \
    && mkdir -p input output models temp user

CMD ["/opt/runpod/start.sh"]
