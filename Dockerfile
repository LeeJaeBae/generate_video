# Start from the base image
FROM runpod/worker-comfyui:5.1.0-base

RUN rm -rf /workspace && \
    ln -s /runpod-volume/runpod-slim/ComfyUI /workspace

# Install required packages and custom nodes
RUN pip install huggingface-hub
RUN comfy-node-install https://github.com/olduvai-jp/ComfyUI-HfLoader

COPY . .

CMD ["python", "-u", "/ComfyUI/main.py", "--disable-auto-launch", "--disable-metadata", "--listen", "--verbose", "DEBUG", "--log-stdout"]

CMD ["python", "-u", "handler.py"]