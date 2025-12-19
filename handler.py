import runpod
import os
import websocket
import base64
import json
import uuid
import logging
import urllib.request
import urllib.parse
import time

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

server_address = os.getenv('SERVER_ADDRESS', '127.0.0.1')
client_id = str(uuid.uuid4())

# 이미지 저장 디렉토리
INPUT_DIR = "/ComfyUI/input"


def save_base64_image(name: str, base64_data: str) -> str:
    """Base64 이미지를 파일로 저장하고 경로 반환"""
    try:
        os.makedirs(INPUT_DIR, exist_ok=True)

        decoded_data = base64.b64decode(base64_data)
        file_path = os.path.join(INPUT_DIR, name)

        with open(file_path, 'wb') as f:
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
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request(url, data=data)
    return json.loads(urllib.request.urlopen(req).read())


def get_history(prompt_id):
    url = f"http://{server_address}:8188/history/{prompt_id}"
    logger.info(f"Getting history from: {url}")
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read())


def get_videos(ws, prompt):
    prompt_id = queue_prompt(prompt)['prompt_id']
    output_videos = {}

    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message['type'] == 'executing':
                data = message['data']
                if data['node'] is None and data['prompt_id'] == prompt_id:
                    break
        else:
            continue

    history = get_history(prompt_id)[prompt_id]
    for node_id in history['outputs']:
        node_output = history['outputs'][node_id]
        videos_output = []
        if 'gifs' in node_output:
            for video in node_output['gifs']:
                with open(video['fullpath'], 'rb') as f:
                    video_data = base64.b64encode(f.read()).decode('utf-8')
                videos_output.append(video_data)
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

    # 2) images 배열 처리: [{ name: string, image: base64 }]
    images = job_input.get("images", [])
    for img in images:
        name = img.get("name")
        image_data = img.get("image")

        if not name or not image_data:
            logger.warning(f"이미지 정보 누락: name={name}, image={'있음' if image_data else '없음'}")
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
    for node_id in videos:
        if videos[node_id]:
            return {"video": videos[node_id][0]}

    return {"error": "비디오를 찾을 수 없습니다."}


runpod.serverless.start({"handler": handler})
