# Use specific version of nvidia cuda image
FROM wlsdml1114/multitalk-base:1.7 as runtime

WORKDIR /

# 런타임 패키지 설치
RUN pip install -U "huggingface_hub[hf_transfer]" runpod websocket-client

# 로컬 파일 복사
COPY . .
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]