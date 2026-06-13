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
            "aspect_ratio": "9:16",
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
                       tts_sec: float = None) -> bool:
    """beat 1개 → fal.ai Kling 클립 생성. 20초 beat는 10초 × 2클립 concat.

    tts_sec: 실측 TTS 길이 — 있으면 v5 길이 결정 규칙으로 5s/10s 선택.
    없으면 beat.duration_sec 폴백.
    """
    _check_key()

    char_path = char_image_path or _CHAR_IMAGE
    beat_name = beat.get("beat", "꿀팁3단")
    emotion   = beat.get("emotion", "평온")
    duration  = _kling_duration(tts_sec) if tts_sec is not None else beat.get("duration_sec", 5)
    prompt    = _build_prompt(beat_name, emotion)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # 레퍼런스 이미지를 fal.ai에 업로드해 URL 확보
    print(f"    레퍼런스 업로드: {char_path}")
    image_url = fal_client.upload_file(char_path)

    if duration <= 10:
        print(f"    fal.ai 제출: [{beat_name}/{emotion}] {duration}초")
        url = _generate_clip(image_url, prompt, duration)
        _download(url, output_path)

    else:
        n_clips = (duration + 9) // 10
        part_paths = []
        for i in range(n_clips):
            part_path = output_path.replace(".mp4", f"_part{i}.mp4")
            print(f"    fal.ai 제출: [{beat_name}/{emotion}] part {i+1}/{n_clips}")
            url = _generate_clip(image_url, prompt, 10)
            _download(url, part_path)
            part_paths.append(part_path)

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
                       char_image_path: str = None,
                       tts_durations: list[float] = None,
                       selected_images: dict = None) -> list[str]:
    """스크립트의 모든 beat에 대해 fal.ai 클립 생성.

    tts_durations: measure_beat_durations()로 측정한 실측 TTS 길이 목록.
    selected_images: {beat_idx_str: image_path} — 이미지 게이트에서 선택된 경로.
                     제공 시 해당 beat는 선택 이미지를 I2V 입력으로 사용.
    """
    os.makedirs(output_dir, exist_ok=True)
    clip_paths = []

    for i, beat in enumerate(script_data.get("beats", [])):
        out = os.path.join(output_dir, f"beat_{i:02d}.mp4")
        tts_sec = tts_durations[i] if tts_durations and i < len(tts_durations) else None
        beat_img = (selected_images or {}).get(str(i)) or char_image_path
        if os.path.exists(out):
            print(f"  beat_{i:02d} 기존 클립 재사용")
        else:
            generate_beat_clip(beat, out, beat_img, tts_sec=tts_sec)
        clip_paths.append(out)

    return clip_paths
