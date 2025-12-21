#!/bin/bash
set -euo pipefail

# Select ComfyUI root (prefer /ComfyUI, fallback candidates)
if [ -f "/ComfyUI/main.py" ]; then
  COMFY_ROOT="/ComfyUI"
elif [ -f "/workspace/main.py" ]; then
  COMFY_ROOT="/workspace"
elif [ -f "/workspace/ComfyUI/main.py" ]; then
  COMFY_ROOT="/workspace/ComfyUI"
else
  echo "Error: ComfyUI main.py not found in /ComfyUI, /workspace, or /workspace/ComfyUI"
  exit 1
fi

# Activate venv if present (try common locations)
if [ -f "${COMFY_ROOT}/.venv-cu128/bin/activate" ]; then
  source "${COMFY_ROOT}/.venv-cu128/bin/activate"
elif [ -f "/opt/venv/.venv-cu128/bin/activate" ]; then
  source "/opt/venv/.venv-cu128/bin/activate"
elif [ -f "/opt/venv/bin/activate" ]; then
  source "/opt/venv/bin/activate"
else
  echo "Warning: venv activate script not found. Continuing with system python."
fi

# Optional args (avoid hard-crash if unsupported)
COMFY_ARGS=(--listen 0.0.0.0 --port 8188)

# Toggle sage attention via env var (default off)
# export USE_SAGE_ATTENTION=1 in RunPod env if you want
if [ "${USE_SAGE_ATTENTION:-0}" = "1" ]; then
  COMFY_ARGS+=(--use-sage-attention)
fi

echo "Starting ComfyUI in the background..."
python -u "${COMFY_ROOT}/main.py" "${COMFY_ARGS[@]}" &
COMFY_PID=$!

# If comfy dies, kill container (and handler) too
cleanup() {
  if kill -0 "$COMFY_PID" >/dev/null 2>&1; then
    kill "$COMFY_PID" || true
  fi
}
trap cleanup EXIT

echo "Waiting for ComfyUI to be ready..."
max_wait=120
elapsed=0

# Require a couple consecutive successes to reduce race
ok=0
while [ $elapsed -lt $max_wait ]; do
  if curl -fsS "http://127.0.0.1:8188/" >/dev/null 2>&1; then
    ok=$((ok+1))
    if [ $ok -ge 3 ]; then
      echo "ComfyUI is ready!"
      break
    fi
  else
    ok=0
  fi

  # If comfy died while waiting, fail fast
  if ! kill -0 "$COMFY_PID" >/dev/null 2>&1; then
    echo "Error: ComfyUI process exited during startup"
    exit 1
  fi

  sleep 2
  elapsed=$((elapsed+2))
  echo "Waiting for ComfyUI... (${elapsed}/${max_wait})"
done

if [ $elapsed -ge $max_wait ]; then
  echo "Error: ComfyUI failed to start within ${max_wait} seconds"
  exit 1
fi

echo "Starting the handler..."
exec python -u /handler.py
