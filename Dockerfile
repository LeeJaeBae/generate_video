# Start from the base image
FROM runpod/worker-comfyui:5.1.0-base

# /workspace 를 네트워크 볼륨(또는 영구 볼륨)로 연결
RUN rm -rf /workspace && \
    ln -s /runpod-volume/runpod-slim/ComfyUI /workspace

WORKDIR /workspace

# (VHS VideoCombine 등 영상 노드 쓰면 ffmpeg 필요)
# base 이미지에 이미 들어있을 수도 있지만, 없으면 조용히 터져서 그냥 박아둠.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# 빌드 컨텍스트 복사 (requirements.txt, entrypoint.sh, workflow 등)
COPY . .

# Python deps
# /requirements.txt 를 쓰고 있으니 그 경로 유지
RUN pip install --upgrade pip && \
    pip install -r /requirements.txt

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
    comfy-node-install https://github.com/kijai/ComfyUI-WanVideoWrapper

# 각 커스텀 노드 폴더에 requirements.txt 가 있으면 전부 설치
RUN bash -lc 'set -e; \
  for d in /workspace/custom_nodes/*; do \
    if [ -f "$d/requirements.txt" ]; then \
      echo "Installing custom node deps: $d/requirements.txt"; \
      pip install -r "$d/requirements.txt"; \
    fi; \
  done'

# Ensure entrypoint is executable
RUN chmod +x /entrypoint.sh

# Run ComfyUI (background) + handler (foreground)
CMD ["/bin/bash", "/entrypoint.sh"]
