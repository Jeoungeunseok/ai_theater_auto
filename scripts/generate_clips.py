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

_BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CHAR_IMAGE = os.path.join(_BASE_DIR, os.getenv("PANGI_BODY", "assets/pang/base/body_front.png"))
_EYES_DIR   = os.path.join(_BASE_DIR, "assets", "pang", "eyes")

# fal.ai Kling I2V 모델 ID
_FAL_MODEL = "fal-ai/kling-video/v3/pro/image-to-video"

# ── 감정 → eyes 파일명 (영문) ───────────────────────────
_EMOTION_FILE = {
    "평온":   "calm",
    "기쁨":   "joy",
    "신남":   "excited",
    "설렘":   "thrilled",
    "뿌듯함": "proud",
    "자신감": "confident",
    "슬픔":   "sad",
    "분노":   "angry",
    "무서움": "scared",
    "충격":   "shocked",
    "심술":   "mischievous",
    "멍함":   "dazed",
    "과부하": "overwhelmed",
    "재부팅": "rebooting",
}

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

def _build_prompt(beat_name: str, emotion: str,
                  dialogue: str = "", emphasis: str = "",
                  video_prompt: str = "", is_chained: bool = False) -> str:
    emotion_desc = _EMOTION_EN.get(emotion, "neutral expression")
    motion_desc  = _BEAT_MOTION.get(beat_name, "talking expressively")

    # 체이닝: 시작 프레임이 직전 컷의 끝 포즈 → 감정이 변해가는 과정을 지시
    if is_chained:
        emotion_part = f"The character's expression smoothly transitions into {emotion_desc}. "
    else:
        emotion_part = f"Emotion: {emotion_desc}. "

    if video_prompt:
        return (
            f"{emotion_part}Motion: {motion_desc}. "
            f"{video_prompt}"
        )

    # 폴백: 템플릿 조립
    scene_part = ""
    if dialogue:
        scene_part = f"Scene context: '{dialogue}'. "
    if emphasis:
        scene_part += f"Key visual element prominently shown: '{emphasis}'. "

    return (
        f"{emotion_part}Motion: {motion_desc}. "
        f"{scene_part}"
        f"Background matches the scene context naturally. "
        f"3D cartoon animation style, vertical 9:16 format, character centered."
    )


# ── fal.ai API ────────────────────────────────────────────

def _check_key():
    if not os.getenv("FAL_KEY"):
        raise ValueError("FAL_KEY 미설정 — fal.ai API 키를 .env에 추가하세요")


def _kling_duration(tts_sec: float, hold_sec: float = 0.15) -> int:
    """클립 길이 = TTS + 동작 유지(hold) + 여유 1초. v3 지원 범위 3~15초 클리핑.

    렌더는 tts+hold로 트림하므로, 클립은 그보다 충분히 길어야 잘림 없음.
    """
    return max(3, min(15, int(tts_sec + hold_sec + 0.5) + 1))


def _generate_clip(image_url: str, prompt: str, duration_sec: int,
                   eye_url: str = None, body_url: str = None) -> str:
    """fal.ai Kling v3/pro I2V 요청 → 영상 URL 반환.

    eye_url + body_url 둘 다 있을 때만 elements 활성화.
    elements[0]: 감정(eye) 정면 + 전신(body) 레퍼런스 → @Element1로 캐릭터 고정.
    """
    arguments = {
        "start_image_url": image_url,
        "prompt": prompt,
        "negative_prompt": "different character, redesign, human, realistic, text, watermark, blurry",
        "duration": duration_sec,
        "generate_audio": False,
    }

    handler = fal_client.submit(_FAL_MODEL, arguments=arguments)
    result = handler.get()
    return result["video"]["url"]


def _download(url: str, output_path: str):
    resp = requests.get(url, timeout=120, stream=True)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)


def _extract_last_frame(video_path: str, output_path: str) -> str:
    """클립 마지막 프레임을 PNG로 추출 — 다음 컷 체이닝 시작 프레임용."""
    cmd = [
        "ffmpeg", "-y", "-sseof", "-0.1", "-i", video_path,
        "-frames:v", "1", "-q:v", "2", output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not os.path.exists(output_path):
        raise RuntimeError(f"마지막 프레임 추출 실패:\n{result.stderr}")
    return output_path


# ── beat 클립 생성 ────────────────────────────────────────

def generate_beat_clip(beat: dict, output_path: str,
                       char_image_path: str = None,
                       tts_sec: float = None,
                       scene_setting: str = "",
                       start_image_path: str = None) -> int:
    """beat 1개 → fal.ai Kling v3 클립 생성. 생성된 클립 초(duration) 반환.

    v3는 3~15초 네이티브 지원 — concat 불필요.
    tts_sec: 실측 TTS 길이 — 있으면 _kling_duration()으로 초 결정.
    없으면 beat.duration_sec 폴백.
    start_image_path: 체이닝 시작 프레임(직전 컷 끝 프레임). 있으면 eyes 대신 사용.
    """
    _check_key()

    char_path = char_image_path or _CHAR_IMAGE
    beat_name    = beat.get("beat", "꿀팁3단")
    emotion      = beat.get("emotion", "평온")
    dialogue     = beat.get("dialogue", "")
    emphasis     = beat.get("emphasis", "")
    video_prompt = beat.get("video_prompt", "")
    hold_sec     = max(0.1, min(2.0, float(beat.get("action_hold_sec", 0.15) or 0.15)))
    duration     = _kling_duration(tts_sec, hold_sec) if tts_sec is not None else min(15, max(3, int(beat.get("duration_sec", 5))))
    full_video_prompt = f"{scene_setting} {video_prompt}".strip() if scene_setting else video_prompt

    is_chained = bool(start_image_path and os.path.exists(start_image_path))
    prompt = _build_prompt(beat_name, emotion, dialogue, emphasis,
                           full_video_prompt, is_chained=is_chained)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # 체이닝: 직전 컷 끝 프레임 / 첫 컷: eyes/{영문}.png
    if is_chained:
        start_path = start_image_path
    else:
        eye_file   = _EMOTION_FILE.get(emotion, "calm")
        eye_path   = os.path.join(_EYES_DIR, f"{eye_file}.png")
        start_path = eye_path if os.path.exists(eye_path) else char_path
    print(f"    시작 프레임 업로드: {os.path.basename(start_path)}"
          f"{' (체이닝)' if is_chained else ''}")
    image_url = fal_client.upload_file(start_path)

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
    frames_dir = os.path.join(output_dir, "_frames")
    os.makedirs(frames_dir, exist_ok=True)
    clip_paths = []
    clip_seconds = []

    scene_setting = script_data.get("scene_setting", "")
    prev_frame = None  # 직전 컷 끝 프레임 — 체이닝 시작점

    for i, beat in enumerate(script_data.get("beats", [])):
        out = os.path.join(output_dir, f"beat_{i:02d}.mp4")
        tts_sec = tts_durations[i] if tts_durations and i < len(tts_durations) else None
        beat_img = (selected_images or {}).get(str(i)) or char_image_path
        if os.path.exists(out):
            print(f"  beat_{i:02d} 기존 클립 재사용")
            clip_seconds.append(0)
        else:
            # 첫 컷은 eyes, 이후 컷은 직전 클립 끝 프레임에서 이어서 시작
            secs = generate_beat_clip(beat, out, beat_img, tts_sec=tts_sec,
                                      scene_setting=scene_setting,
                                      start_image_path=prev_frame)
            clip_seconds.append(secs)
        clip_paths.append(out)

        # 다음 컷 체이닝용 끝 프레임 추출
        prev_frame = os.path.join(frames_dir, f"end_{i:02d}.png")
        _extract_last_frame(out, prev_frame)

    return clip_paths, clip_seconds
