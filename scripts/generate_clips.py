"""
fal.ai Kling I2V — beat별 팡이 영상 클립 생성
레퍼런스 이미지 + 프롬프트 → fal.ai Kling Image-to-Video → 클립 저장
"""
import os
import subprocess
import requests
from dotenv import load_dotenv

load_dotenv()

try:
    import fal_client
except ImportError:
    raise ImportError("fal-client 필요: pip install fal-client")

_CHAR_IMAGE = os.getenv("PANGI_BODY", "assets/pang/base/body_front.png")

# fal.ai Kling I2V 모델 ID
_FAL_MODEL = "fal-ai/kling-video/v3/pro/image-to-video"

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
    "전개1":   "raising one finger, leaning forward to deliver the first point with energy and presence",
    "전개2":   "gesturing expressively with both hands, engaging storytelling pose with rhythmic head nods",
    "전개3":   "decisive gesture — snap or clap — punctuating the final key point, triumphant pose",
    "마무리":  "winking at the camera, giving a thumbs up, cheerful wave goodbye",
}


# ── 프롬프트 빌드 ─────────────────────────────────────────

def _build_prompt(beat_name: str, emotion: str) -> str:
    # v4 §2.3: 외형은 레퍼런스로 고정, 프롬프트는 감정·모션만 지정
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


# ── fal.ai API ────────────────────────────────────────────

def _check_key():
    if not os.getenv("FAL_KEY"):
        raise ValueError("FAL_KEY 미설정 — fal.ai API 키를 .env에 추가하세요")


def _kling_duration(tts_sec: float) -> int:
    """TTS 길이 + 여유 0.5초, v3 지원 범위 3~15초로 클리핑."""
    return max(3, min(15, int(tts_sec + 0.5) + 1))


def _generate_clip(image_url: str, prompt: str, duration_sec: int) -> str:
    """fal.ai에 I2V 요청 → 영상 URL 반환. generate_audio=false(무음) 고정."""
    handler = fal_client.submit(
        _FAL_MODEL,
        arguments={
            "image_url": image_url,
            "prompt": prompt,
            "negative_prompt": "different character, redesign, human, realistic, text, watermark, blurry",
            "duration": duration_sec,
            "generate_audio": False,
        },
    )
    result = handler.get()
    return result["video"]["url"]


def _download(url: str, output_path: str):
    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


# ── beat 클립 생성 ────────────────────────────────────────

def generate_beat_clip(beat: dict, output_path: str,
                       char_image_path: str = None,
                       tts_sec: float = None) -> int:
    """beat 1개 → fal.ai Kling v3 클립 생성. 생성된 클립 초(duration) 반환.

    v3는 3~15초 네이티브 지원 — concat 불필요.
    tts_sec: 실측 TTS 길이 — 있으면 _kling_duration()으로 초 결정.
    없으면 beat.duration_sec 폴백.
    """
    _check_key()

    char_path = char_image_path or _CHAR_IMAGE
    beat_name = beat.get("beat", "꿀팁3단")
    emotion   = beat.get("emotion", "평온")
    duration  = _kling_duration(tts_sec) if tts_sec is not None else min(15, max(3, int(beat.get("duration_sec", 5))))
    prompt    = _build_prompt(beat_name, emotion)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    print(f"    레퍼런스 업로드: {char_path}")
    image_url = fal_client.upload_file(char_path)

    print(f"    fal.ai 제출: [{beat_name}/{emotion}] {duration}초")
    url = _generate_clip(image_url, prompt, duration)
    _download(url, output_path)

    print(f"    클립 저장: {output_path}")
    return duration


def generate_all_clips(script_data: dict, output_dir: str,
                       char_image_path: str = None,
                       tts_durations: list[float] = None,
                       selected_images: dict = None) -> tuple[list[str], list[int]]:
    """스크립트의 모든 beat에 대해 fal.ai 클립 생성.

    Returns: (clip_paths, clip_seconds) — clip_seconds는 실제 생성된 초 수 목록.
             기존 클립 재사용 시 0으로 표시 (비용 중복 차감 방지).
    """
    os.makedirs(output_dir, exist_ok=True)
    clip_paths = []
    clip_seconds = []

    for i, beat in enumerate(script_data.get("beats", [])):
        out = os.path.join(output_dir, f"beat_{i:02d}.mp4")
        tts_sec = tts_durations[i] if tts_durations and i < len(tts_durations) else None
        beat_img = (selected_images or {}).get(str(i)) or char_image_path
        if os.path.exists(out):
            print(f"  beat_{i:02d} 기존 클립 재사용")
            clip_seconds.append(0)
        else:
            secs = generate_beat_clip(beat, out, beat_img, tts_sec=tts_sec)
            clip_seconds.append(secs)
        clip_paths.append(out)

    return clip_paths, clip_seconds
