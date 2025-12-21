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
INPUT_DIR = os.getenv("COMFY_INPUT_DIR", "/comfyui/input")
# ComfyUI 출력/임시 디렉토리 (컨테이너 기준)
OUTPUT_DIR = os.getenv("COMFY_OUTPUT_DIR", "/comfyui/output")
TEMP_DIR = os.getenv("COMFY_TEMP_DIR", "/comfyui/temp")


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


def resolve_comfy_file_path(item) -> str | None:
    """
    ComfyUI history outputs의 파일 정보를 실제 경로로 변환.
    - 지원: fullpath / (filename + subfolder + type)
    """
    if not isinstance(item, dict):
        return None

    fullpath = item.get("fullpath")
    if isinstance(fullpath, str) and fullpath:
        return fullpath

    filename = item.get("filename")
    if not isinstance(filename, str) or not filename:
        return None

    subfolder = item.get("subfolder") or ""
    if not isinstance(subfolder, str):
        subfolder = ""

    out_type = item.get("type") or "output"
    base_dir = TEMP_DIR if out_type == "temp" else OUTPUT_DIR
    return os.path.join(base_dir, subfolder, filename)


def normalize_input_image_to_data_url(name: str | None, image_data: str) -> str | None:
    """요청으로 들어온 이미지(base64 or data URL)를 data URL로 정규화"""
    if not isinstance(image_data, str) or not image_data:
        return None
    if image_data.startswith("data:"):
        return image_data
    mime = guess_mime_from_path(name or "")
    return to_data_url(image_data, mime)


def get_outputs(ws, prompt):
    prompt_id = queue_prompt(prompt)["prompt_id"]
    output_videos = {}
    output_images = {}

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

        # ComfyUI 출력 키는 workflow에 따라 다를 수 있어서 images/gifs/videos 모두 처리
        video_files = []
        image_files = []
        if isinstance(node_output, dict):
            if "gifs" in node_output and isinstance(node_output["gifs"], list):
                video_files = node_output["gifs"]
            elif "videos" in node_output and isinstance(node_output["videos"], list):
                video_files = node_output["videos"]

            if "images" in node_output and isinstance(node_output["images"], list):
                image_files = node_output["images"]

        videos_output = []
        for item in video_files:
            fullpath = resolve_comfy_file_path(item)
            if not fullpath:
                continue
            with open(fullpath, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            mime = guess_mime_from_path(fullpath)
            videos_output.append(to_data_url(b64, mime))

        images_output = []
        for item in image_files:
            fullpath = resolve_comfy_file_path(item)
            if not fullpath:
                continue
            with open(fullpath, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            mime = guess_mime_from_path(fullpath)
            images_output.append(to_data_url(b64, mime))

        output_videos[node_id] = videos_output
        output_images[node_id] = images_output

    return {"videos": output_videos, "images": output_images}


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
    outputs = get_outputs(ws, workflow)
    ws.close()

    # 6) 결과 반환
    # 우리 프로젝트의 serverless 결과 파싱이 단순해서(output.videoUrl 형태), data URL로 반환
    video_url = None
    image_url = None

    videos = outputs.get("videos", {}) if isinstance(outputs, dict) else {}
    images = outputs.get("images", {}) if isinstance(outputs, dict) else {}

    if isinstance(videos, dict):
        for _, arr in videos.items():
            if isinstance(arr, list) and arr:
                video_url = arr[0]
                break

    # 1) ComfyUI outputs에서 이미지 1장 우선
    if isinstance(images, dict):
        for _, arr in images.items():
            if isinstance(arr, list) and arr:
                image_url = arr[0]
                break

    # 2) 없으면 입력 이미지(첫 장)로 fallback
    if not image_url and isinstance(job_input.get("images"), list) and job_input["images"]:
        first = job_input["images"][0]
        if isinstance(first, dict):
            image_url = normalize_input_image_to_data_url(
                first.get("name"),
                first.get("data") or first.get("image") or "",
            )

    result = {}
    if video_url:
        result["videoUrl"] = video_url
    if image_url:
        result["imageUrl"] = image_url

    if result:
        return result

    return {"error": "비디오/이미지를 찾을 수 없습니다."}


runpod.serverless.start({"handler": handler})