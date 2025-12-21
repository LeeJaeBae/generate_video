# Start from the base image
FROM runpod/worker-comfyui:5.1.0-base

RUN rm -rf /workspace && \
    ln -s /runpod-volume/runpod-slim/ComfyUI /workspace

# Install required packages and custom nodes
RUN pip install huggingface-hub
RUN comfy-node-install https://github.com/olduvai-jp/ComfyUI-HfLoader

COPY . .

# venv-cu128 to opt/venv/
RUN cp -r /workspace/.venv-cu128 /opt/venv/

# Ensure entrypoint is executable
RUN chmod +x /entrypoint.sh

# Run ComfyUI (background) + handler (foreground)
CMD ["/bin/bash", "/entrypoint.sh"]