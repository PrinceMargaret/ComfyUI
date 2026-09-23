import base64
import json
import os
import time
import uuid
from urllib.parse import urlencode

import requests
import runpod

COMFY_HOST = os.environ.get("COMFY_HOST", "127.0.0.1:8188")
POLL_INTERVAL = float(os.environ.get("COMFY_POLL_INTERVAL_S", "0.25"))
POLL_TIMEOUT = float(os.environ.get("COMFY_POLL_TIMEOUT_S", "600"))
INPUT_DIR = os.environ.get("COMFY_INPUT_DIR", "/comfyui/input")
OUTPUT_KEYS = ("images", "gifs", "videos", "audio")


def wait_for_server():
    deadline = time.time() + float(os.environ.get("COMFY_STARTUP_TIMEOUT_S", "300"))
    url = f"http://{COMFY_HOST}/system_stats"
    last_error = None
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                return
        except requests.RequestException as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"ComfyUI did not become ready at {url}: {last_error}")


def _save_input(item):
    name = os.path.basename(item.get("name") or "input.png")
    if not name or name in (".", "..") or name != item.get("name", name):
        raise ValueError("image name must be a file name")
    raw = item.get("image")
    if not raw:
        raise ValueError(f"image {name} is missing data")
    if raw.startswith("http://") or raw.startswith("https://"):
        response = requests.get(raw, timeout=120)
        response.raise_for_status()
        data = response.content
    else:
        if raw.startswith("data:") and "," in raw:
            raw = raw.split(",", 1)[1]
        data = base64.b64decode(raw)
    os.makedirs(INPUT_DIR, exist_ok=True)
    with open(os.path.join(INPUT_DIR, name), "wb") as handle:
        handle.write(data)


def _workflow(job_input):
    workflow = job_input.get("workflow", job_input.get("prompt"))
    if isinstance(workflow, str):
        workflow = json.loads(workflow)
    if not isinstance(workflow, dict):
        raise ValueError("workflow must be a ComfyUI API prompt")
    prompt = workflow.get("prompt")
    if isinstance(prompt, dict) and any(isinstance(node, dict) and "class_type" in node for node in prompt.values()):
        return prompt
    return workflow


def _queue(workflow):
    response = requests.post(
        f"http://{COMFY_HOST}/prompt",
        json={"prompt": workflow, "client_id": str(uuid.uuid4())},
        timeout=60,
    )
    try:
        body = response.json()
    except ValueError:
        raise RuntimeError(response.text)
    if response.status_code != 200 or "error" in body:
        raise RuntimeError(json.dumps(body))
    return body["prompt_id"]


def _wait(prompt_id):
    deadline = time.time() + POLL_TIMEOUT
    url = f"http://{COMFY_HOST}/history/{prompt_id}"
    while time.time() < deadline:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        entry = response.json().get(prompt_id)
        if entry:
            status = entry.get("status") or {}
            if status.get("status_str") == "error":
                raise RuntimeError(json.dumps(status))
            if status.get("completed", True):
                return entry
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"prompt {prompt_id} did not finish within {POLL_TIMEOUT:.0f}s")


def _collect(entry):
    files = []
    for node_id, output in (entry.get("outputs") or {}).items():
        if not isinstance(output, dict):
            continue
        for key in OUTPUT_KEYS:
            for item in output.get(key) or []:
                if "filename" not in item:
                    continue
                query = urlencode({
                    "filename": item["filename"],
                    "subfolder": item.get("subfolder") or "",
                    "type": item.get("type") or "output",
                })
                response = requests.get(f"http://{COMFY_HOST}/view?{query}", timeout=120)
                response.raise_for_status()
                files.append({
                    "filename": item["filename"],
                    "node_id": node_id,
                    "type": "base64",
                    "data": base64.b64encode(response.content).decode("ascii"),
                })
    return files


def handler(job):
    job_input = job.get("input") or {}
    for image in job_input.get("images") or []:
        _save_input(image)
    prompt_id = _queue(_workflow(job_input))
    result = {"images": _collect(_wait(prompt_id))}
    if os.environ.get("REFRESH_WORKER", "false").lower() == "true":
        result["refresh_worker"] = True
    return result


if __name__ == "__main__":
    wait_for_server()
    runpod.serverless.start({"handler": handler})
