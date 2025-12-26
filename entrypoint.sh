#!/usr/bin/env bash

# Use libtcmalloc for better memory management
TCMALLOC="$(ldconfig -p | grep -Po "libtcmalloc.so.\d" | head -n 1)"
export LD_PRELOAD="${TCMALLOC}"

# Ensure ComfyUI-Manager runs in offline network mode inside the container
comfy-manager-set-mode offline || echo "worker-comfyui - Could not set ComfyUI-Manager network_mode" >&2

echo "worker-comfyui: Starting ComfyUI"

# Allow operators to tweak verbosity; default is INFO (reduce noisy logs like "lowvram: ...").
: "${COMFY_LOG_LEVEL:=INFO}"

# Optional VRAM mode flags for ComfyUI:
# - COMFY_VRAM_MODE=highvram|medvram|lowvram
# - COMFY_EXTRA_ARGS="...": any extra args passed to /comfyui/main.py
: "${COMFY_VRAM_MODE:=}"
: "${COMFY_EXTRA_ARGS:=}"

COMFY_VRAM_FLAG=""
case "${COMFY_VRAM_MODE}" in
  highvram|medvram|lowvram)
    COMFY_VRAM_FLAG="--${COMFY_VRAM_MODE}"
    ;;
  "")
    COMFY_VRAM_FLAG=""
    ;;
  *)
    echo "worker-comfyui: Unknown COMFY_VRAM_MODE='${COMFY_VRAM_MODE}' (supported: highvram|medvram|lowvram). Ignoring." >&2
    COMFY_VRAM_FLAG=""
    ;;
esac

# Serve the API and don't shutdown the container
if [ "$SERVE_API_LOCALLY" == "true" ]; then
    # shellcheck disable=SC2086
    python -u /comfyui/main.py --disable-auto-launch --disable-metadata --listen ${COMFY_VRAM_FLAG} --verbose "${COMFY_LOG_LEVEL}" --log-stdout ${COMFY_EXTRA_ARGS} &

    echo "worker-comfyui: Starting RunPod Handler"
    python -u /handler.py --rp_serve_api --rp_api_host=0.0.0.0
else
    # shellcheck disable=SC2086
    python -u /comfyui/main.py --disable-auto-launch --disable-metadata ${COMFY_VRAM_FLAG} --verbose "${COMFY_LOG_LEVEL}" --log-stdout ${COMFY_EXTRA_ARGS} &

    echo "worker-comfyui: Starting RunPod Handler"
    python -u /handler.py
fi