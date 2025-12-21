#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Select ComfyUI root (prefer /ComfyUI, fallback to /workspace)
COMFY_ROOT=""
if [ -f "/ComfyUI/main.py" ]; then
    COMFY_ROOT="/ComfyUI"
elif [ -f "/workspace/main.py" ]; then
    COMFY_ROOT="/workspace"
else
    echo "Error: ComfyUI main.py not found in /ComfyUI or /workspace"
    exit 1
fi

# Activate venv if present (try common locations)
if [ -f "${COMFY_ROOT}/.venv-cu128/bin/activate" ]; then
    # use venv-cu128 inside ComfyUI root
    source "${COMFY_ROOT}/.venv-cu128/bin/activate"
elif [ -f "/opt/venv/.venv-cu128/bin/activate" ]; then
    # copied by Dockerfile
    source "/opt/venv/.venv-cu128/bin/activate"
elif [ -f "/opt/venv/bin/activate" ]; then
    source "/opt/venv/bin/activate"
else
    echo "Warning: venv activate script not found. Continuing with system python."
fi

# Start ComfyUI in the background
echo "Starting ComfyUI in the background..."
python -u "${COMFY_ROOT}/main.py" --listen 0.0.0.0 --port 8188 --use-sage-attention &

# Wait for ComfyUI to be ready
echo "Waiting for ComfyUI to be ready..."
max_wait=120  # 최대 2분 대기
wait_count=0
while [ $wait_count -lt $max_wait ]; do
    if curl -s http://127.0.0.1:8188/ > /dev/null 2>&1; then
        echo "ComfyUI is ready!"
        break
    fi
    echo "Waiting for ComfyUI... ($wait_count/$max_wait)"
    sleep 2
    wait_count=$((wait_count + 2))
done

if [ $wait_count -ge $max_wait ]; then
    echo "Error: ComfyUI failed to start within $max_wait seconds"
    exit 1
fi

# Start the handler in the foreground
# 이 스크립트가 컨테이너의 메인 프로세스가 됩니다.
echo "Starting the handler..."
exec python -u /handler.py