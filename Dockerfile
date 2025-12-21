# Start from the base image
FROM runpod/worker-comfyui:5.1.0-base

# /workspace 는 그대로 두고, /workspace/ComfyUI 만 영구 볼륨으로 연결
RUN rm -rf /workspace/ComfyUI && \
    ln -s /runpod-volume/runpod-slim/ComfyUI /workspace/ComfyUI

WORKDIR /

# (VHS VideoCombine 등 영상 노드 쓰면 ffmpeg 필요)
# base 이미지에 이미 들어있을 수도 있지만, 없으면 조용히 터져서 그냥 박아둠.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# Python deps
# (경로를 고정해서 entrypoint/handler 가 /workspace 심볼릭 링크 영향 안 받게 함)
COPY requirements.txt /requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /requirements.txt

# Worker files (absolute paths)
COPY entrypoint.sh /entrypoint.sh
COPY handler.py /handler.py


# Custom nodes install
# - HfLoader (네가 이미 설치하던 것)
# - rgthree (Power Lora Loader / Any Switch / Seed 등)
# - VideoHelperSuite (VHS_VideoCombine 등)
# - QwenEditUtils (TextEncodeQwenImageEditPlus 계열)
# - WanVideoWrapper (WanImageToVideo, WanVideoNAG 계열이 필요할 때)
RUN comfy-node-install https://github.com/olduvai-jp/ComfyUI-HfLoader && \
    comfy-node-install https://github.com/rgthree/rgthree-comfy && \
    comfy-node-install https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite && \
    comfy-node-install https://github.com/lrzjason/Comfyui-QwenEditUtils && \
    comfy-node-install https://github.com/kijai/ComfyUI-WanVideoWrapper && \
    comfy-node-install https://github.com/kijai/ComfyUI-KJNodes

# 각 커스텀 노드 폴더에 requirements.txt 가 있으면 전부 설치
RUN bash -lc 'set -e; \
  for d in /workspace/ComfyUI/custom_nodes/*; do \
    if [ -f "$d/requirements.txt" ]; then \
      echo "Installing custom node deps: $d/requirements.txt"; \
      pip install -r "$d/requirements.txt"; \
    fi; \
  done'

# Ensure entrypoint is executable
RUN chmod +x /entrypoint.sh

# entrypoint.sh 실행 (Dockerfile 위치에서 실행)
ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
