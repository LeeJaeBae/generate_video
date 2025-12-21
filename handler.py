import runpod
import os
import websocket
import base64
import json
import uuid
import logging
import urllib.request
import time

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

server_address = os.getenv("SERVER_ADDRESS", "127.0.0.1")
client_id = str(uuid.uuid4())

# 이미지 저장 디렉토리 (ComfyUI 컨테이너 기준)
INPUT_DIR = os.getenv("COMFY_INPUT_DIR", "/ComfyUI/input")


def save_base64_image(name: str, base64_data: str) -> str:
    """Base64 이미지를 파일로 저장하고 경로 반환"""
    try:
        os.makedirs(INPUT_DIR, exist_ok=True)

        decoded_data = base64.b64decode(base64_data)
        file_path = os.path.join(INPUT_DIR, name)

        with open(file_path, "wb") as f:
            f.write(decoded_data)

        logger.info(f"✅ 이미지 저장 완료: {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"❌ 이미지 저장 실패: {e}")
        raise Exception(f"이미지 저장 실패: {e}")


def queue_prompt(prompt):
    url = f"http://{server_address}:8188/prompt"
    logger.info(f"Queueing prompt to: {url}")
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.loads(urllib.request.urlopen(req).read())


def get_history(prompt_id):
    url = f"http://{server_address}:8188/history/{prompt_id}"
    logger.info(f"Getting history from: {url}")
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read())


def guess_mime_from_path(file_path: str) -> str:
    _, ext = os.path.splitext(file_path)
    ext = (ext or "").lower()
    if ext == ".mp4":
        return "video/mp4"
    if ext == ".webm":
        return "video/webm"
    if ext == ".mov":
        return "video/quicktime"
    if ext == ".mkv":
        return "video/x-matroska"
    if ext == ".gif":
        return "image/gif"
    if ext in [".png"]:
        return "image/png"
    if ext in [".jpg", ".jpeg"]:
        return "image/jpeg"
    if ext in [".webp"]:
        return "image/webp"
    return "application/octet-stream"


def to_data_url(b64: str, mime: str) -> str:
    return f"data:{mime};base64,{b64}"


def get_videos(ws, prompt):
    prompt_id = queue_prompt(prompt)["prompt_id"]
    output_videos = {}

    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message.get("type") == "executing":
                data = message.get("data", {})
                if data.get("node") is None and data.get("prompt_id") == prompt_id:
                    break
        else:
            continue

    history = get_history(prompt_id)[prompt_id]

    for node_id in history.get("outputs", {}):
        node_output = history["outputs"][node_id]

        # ComfyUI 출력 키는 workflow에 따라 다를 수 있어서 gifs/videos 둘 다 처리
        files = []
        if isinstance(node_output, dict):
            if "gifs" in node_output and isinstance(node_output["gifs"], list):
                files = node_output["gifs"]
            elif "videos" in node_output and isinstance(node_output["videos"], list):
                files = node_output["videos"]

        videos_output = []
        for item in files:
            fullpath = item.get("fullpath") if isinstance(item, dict) else None
            if not fullpath:
                continue
            with open(fullpath, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            mime = guess_mime_from_path(fullpath)
            videos_output.append(to_data_url(b64, mime))

        output_videos[node_id] = videos_output

    return output_videos


def wait_for_comfyui():
    """ComfyUI 서버가 준비될 때까지 대기"""
    http_url = f"http://{server_address}:8188/"
    logger.info(f"ComfyUI 서버 대기 중: {http_url}")

    max_attempts = 180
    for attempt in range(max_attempts):
        try:
            urllib.request.urlopen(http_url, timeout=5)
            logger.info(f"✅ ComfyUI 서버 연결 성공 (시도 {attempt+1})")
            return True
        except Exception as e:
            logger.warning(f"서버 대기 중 (시도 {attempt+1}/{max_attempts}): {e}")
            if attempt == max_attempts - 1:
                raise Exception("ComfyUI 서버에 연결할 수 없습니다.")
            time.sleep(1)


def handler(job):
    job_input = job.get("input", {})
    logger.info(f"Received job input keys: {list(job_input.keys())}")

    # 1) workflow 받기 (필수)
    workflow = job_input.get("workflow")
    if not workflow:
        return {"error": "workflow 필드가 필요합니다."}

    if isinstance(workflow, str):
        try:
            workflow = json.loads(workflow)
        except json.JSONDecodeError as e:
            return {"error": f"workflow JSON 파싱 실패: {e}"}

    # 2) images 배열 처리 (우리 프로젝트: [{ name, data(base64) }])
    #    다른 코드 호환: image 키도 지원
    images = job_input.get("images", [])
    if isinstance(images, list):
        for img in images:
            if not isinstance(img, dict):
                continue
            name = img.get("name")
            image_data = img.get("data") or img.get("image")  # data 우선

            if not name or not image_data:
                logger.warning(
                    f"이미지 정보 누락: name={name}, data={'있음' if img.get('data') else '없음'}, image={'있음' if img.get('image') else '없음'}"
                )
                continue

            save_base64_image(name, image_data)

    # 3) ComfyUI 서버 대기
    wait_for_comfyui()

    # 4) WebSocket 연결
    ws_url = f"ws://{server_address}:8188/ws?clientId={client_id}"
    logger.info(f"WebSocket 연결: {ws_url}")

    ws = websocket.WebSocket()
    max_attempts = 36  # 3분 (5초 간격)

    for attempt in range(max_attempts):
        try:
            ws.connect(ws_url)
            logger.info(f"✅ WebSocket 연결 성공 (시도 {attempt+1})")
            break
        except Exception as e:
            logger.warning(f"WebSocket 연결 실패 (시도 {attempt+1}/{max_attempts}): {e}")
            if attempt == max_attempts - 1:
                raise Exception("WebSocket 연결 시간 초과")
            time.sleep(5)

    # 5) 워크플로우 실행
    videos = get_videos(ws, workflow)
    ws.close()

    # 6) 결과 반환
    # 우리 프로젝트의 serverless 결과 파싱이 단순해서(output.videoUrl 형태), data URL로 반환
    for node_id, arr in videos.items():
        if arr:
            return {"videoUrl": arr[0]}

    return {"error": "비디오를 찾을 수 없습니다."}


runpod.serverless.start({"handler": handler})