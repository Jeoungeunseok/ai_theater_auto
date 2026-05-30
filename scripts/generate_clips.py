"""
Kling AI Image-to-Video — beat별 팡이 영상 클립 생성
레퍼런스 이미지(캐릭터) + 감정 이미지 + 상황 프롬프트 → 영상 클립
"""
import os
import time
import base64
import json
import requests
from dotenv import load_dotenv

load_dotenv()

try:
    import jwt
except ImportError:
    raise ImportError("PyJWT 필요: pip install PyJWT")

_BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KLING_URL  = "https://api.klingai.com"
_CHAR_IMAGE = os.getenv("PANGI_BODY", "assets/pang/base/body_front.png")

# ── 감정 영문 설명 ────────────────────────────────────────
_EMOTION_EN = {
    "평온":   "calm and neutral expression",
    "기쁨":   "happy and joyful expression",
    "신남":   "excited and energetic expression",
    "설렘":   "thrilled and anticipating expression",
    "뿌듯함": "proud and satisfied expression",
    "자신감": "confident and assertive expression",
    "슬픔":   "sad and droopy expression",
    "분노":   "angry and frustrated expression",
    "무서움": "scared and nervous expression",
    "충격":   "shocked and surprised expression",
    "심술":   "mischievous and sly expression",
    "멍함":   "dazed and confused expression",
    "과부하": "overwhelmed and overloaded expression",
    "재부팅": "rebooting and resetting expression",
}

# ── beat별 모션 설명 ──────────────────────────────────────
_BEAT_MOTION = {
    "후킹":    "pointing playfully at the viewer, leaning forward with a knowing smirk, provocative gesture",
    "본심수신": "antenna flashing and glowing, body spinning slightly with surprise, signal receiving animation",
    "꿀팁3단": "gesturing confidently with hands, explaining expressively, coaching motion with head nodding",
    "마무리":  "winking at the camera, giving a thumbs up, cheerful wave goodbye",
}


# ── Kling API ─────────────────────────────────────────────

def _make_token() -> str:
    ak = os.getenv("KLING_ACCESS_KEY_ID")
    sk = os.getenv("KLING_ACCESS_KEY_SECRET")
    if not ak or not sk:
        raise ValueError("KLING_ACCESS_KEY_ID / KLING_ACCESS_KEY_SECRET 미설정")
    payload = {
        "iss": ak,
        "exp": int(time.time()) + 1800,
        "nbf": int(time.time()) - 5,
    }
    return jwt.encode(payload, sk, algorithm="HS256")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_make_token()}",
        "Content-Type": "application/json",
    }


def _encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _build_prompt(beat_name: str, emotion: str, dialogue_excerpt: str) -> str:
    # v4 §2.3 일관성 — 외형(얼굴 구조·비율·색)은 레퍼런스 이미지로 고정하고,
    # 프롬프트는 감정 표정·안테나·모션만 지정한다. (팡이 = 와이파이 의인화, "파란 로봇" 아님)
    emotion_desc = _EMOTION_EN.get(emotion, "neutral expression")
    motion_desc  = _BEAT_MOTION.get(beat_name, "talking expressively")
    return (
        f"팡이(Pangi), an anthropomorphic Wi-Fi signal mascot character. "
        f"Keep the exact same character design, face structure, body proportions and colors "
        f"as the reference image — do NOT redesign the character. "
        f"Only animate the expression and the signal antenna: {emotion_desc}. "
        f"Motion: {motion_desc}. "
        f"3D cartoon animation style, clean simple background, vertical 9:16 format, "
        f"character centered in frame."
    )


def _submit_task(char_image_b64: str, prompt: str, duration_sec: int) -> str:
    """Kling 작업 제출 → task_id 반환."""
    # Kling은 최대 10초 단위 — 5초 or 10초
    kling_duration = "10" if duration_sec >= 10 else "5"

    # v4 §2.3: 마스터 레퍼런스(image) 1장만 주입해 캐릭터를 고정.
    # 감정은 프롬프트로 지정하므로 부분(눈) 이미지를 image_tail로 넣지 않는다.
    body = {
        "model_name": "kling-v1-5",
        "image": char_image_b64,
        "prompt": prompt,
        "negative_prompt": "different character, redesign, human, realistic, text, watermark, blurry",
        "cfg_scale": 0.5,
        "mode": "std",
        "duration": kling_duration,
    }

    resp = requests.post(
        f"{_KLING_URL}/v1/videos/image2video",
        headers=_headers(),
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Kling 오류: {data.get('message')}")
    return data["data"]["task_id"]


def _poll_task(task_id: str, timeout: int = 300) -> str:
    """작업 완료 대기 → 영상 URL 반환."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.get(
            f"{_KLING_URL}/v1/videos/image2video/{task_id}",
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        status = data.get("task_status")

        if status == "succeed":
            return data["task_result"]["videos"][0]["url"]
        if status == "failed":
            raise RuntimeError(f"Kling 생성 실패: {data.get('task_status_msg')}")

        print(f"    생성 중... ({status})")
        time.sleep(8)

    raise TimeoutError(f"Kling 타임아웃: {timeout}초")


def _download(url: str, output_path: str):
    resp = requests.get(url, timeout=60, stream=True)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


# ── beat 클립 생성 ────────────────────────────────────────

def generate_beat_clip(beat: dict, output_path: str,
                       char_image_path: str = None) -> bool:
    """
    beat 1개 → Kling 클립 생성.
    20초 beat는 10초 클립 2개를 FFmpeg로 이어붙임.
    """
    char_path  = char_image_path or _CHAR_IMAGE
    beat_name  = beat.get("beat", "꿀팁3단")
    emotion    = beat.get("emotion", "평온")
    dialogue   = beat.get("dialogue", "")
    duration   = beat.get("duration_sec", 5)

    char_b64   = _encode_image(char_path)
    prompt     = _build_prompt(beat_name, emotion, dialogue[:50])

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # 10초 이하 → 1회 생성
    if duration <= 10:
        print(f"    Kling 제출: [{beat_name}/{emotion}] {duration}초")
        task_id = _submit_task(char_b64, prompt, duration)
        url = _poll_task(task_id)
        _download(url, output_path)

    # 10초 초과 → 여러 클립 생성 후 concat
    else:
        import subprocess
        n_clips = (duration + 9) // 10  # 10초 단위 올림
        part_paths = []
        for i in range(n_clips):
            part_path = output_path.replace(".mp4", f"_part{i}.mp4")
            print(f"    Kling 제출: [{beat_name}/{emotion}] part {i+1}/{n_clips}")
            task_id = _submit_task(char_b64, prompt, 10)
            url = _poll_task(task_id)
            _download(url, part_path)
            part_paths.append(part_path)

        # concat
        list_file = output_path.replace(".mp4", "_list.txt")
        with open(list_file, "w") as f:
            for p in part_paths:
                f.write(f"file '{os.path.abspath(p)}'\n")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", list_file, "-c", "copy", output_path],
            capture_output=True, check=True,
        )
        os.remove(list_file)
        for p in part_paths:
            os.remove(p)

    print(f"    클립 저장: {output_path}")
    return True


def generate_all_clips(script_data: dict, output_dir: str,
                       char_image_path: str = None) -> list[str]:
    """스크립트의 모든 beat에 대해 Kling 클립 생성."""
    os.makedirs(output_dir, exist_ok=True)
    clip_paths = []

    for i, beat in enumerate(script_data.get("beats", [])):
        out = os.path.join(output_dir, f"beat_{i:02d}.mp4")
        if os.path.exists(out):
            print(f"  beat_{i:02d} 기존 클립 재사용")
        else:
            generate_beat_clip(beat, out, char_image_path)
        clip_paths.append(out)

    return clip_paths
