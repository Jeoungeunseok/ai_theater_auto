import asyncio
import json
import os
import re
import subprocess
import yaml
import edge_tts
from dotenv import load_dotenv

load_dotenv()

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 정식 14감정 세트 — pangi_persona.yaml emotions와 동일하게 유지
_EMOTION_MOD: dict[str, tuple[int, int]] = {
    "평온":   (  0,   0),
    "기쁨":   ( +5,  +3),
    "신남":   (+10,  +5),
    "설렘":   ( +5,  +5),
    "뿌듯함": ( +3,  +2),
    "자신감": ( +5,  +2),
    "슬픔":   (-10,  -5),
    "분노":   (+10,  -8),
    "무서움": ( -8,  +5),
    "충격":   (+12,  +8),
    "심술":   ( +5,  -5),
    "멍함":   (-15,  -3),
    "과부하": (+15, +10),
    "재부팅": (  0,   0),
}


def _load_voice_config() -> tuple[str, str, str]:
    path = os.path.join(_BASE_DIR, "prompts", "pangi_persona.yaml")
    with open(path, encoding="utf-8") as f:
        persona = yaml.safe_load(f)
    v = persona["voice"]
    voice = os.getenv("TTS_VOICE", v["default_speaker"])
    base_rate = os.getenv("TTS_BASE_RATE", v["base_rate"])
    base_pitch = os.getenv("TTS_BASE_PITCH", v["base_pitch"])
    return voice, base_rate, base_pitch


def _apply_emotion(base_rate: str, base_pitch: str, emotion: str) -> tuple[str, str]:
    mod_rate, mod_pitch = _EMOTION_MOD.get(emotion, (0, 0))
    r = int(base_rate.replace("%", "").replace("+", ""))
    p = int(base_pitch.replace("Hz", "").replace("+", ""))
    return f"{r + mod_rate:+d}%", f"{p + mod_pitch:+d}Hz"


def _clean(text: str) -> str:
    emoji = re.compile(
        r"[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0000FE00-\U0000FE0F]+",
        flags=re.UNICODE,
    )
    text = emoji.sub("", text)
    text = re.sub(r"\([^)]*(?:효과|소리|음)[^)]*\)", "", text)
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\?{2,}", "?", text)
    return text.strip()


async def _generate_beats(beats: list, output_dir: str):
    voice, base_rate, base_pitch = _load_voice_config()
    os.makedirs(output_dir, exist_ok=True)

    for i, beat in enumerate(beats):
        emotion = beat.get("emotion", "평온")
        text = _clean(beat.get("dialogue", ""))
        rate, pitch = _apply_emotion(base_rate, base_pitch, emotion)
        out = os.path.join(output_dir, f"beat_{i:02d}.mp3")

        try:
            comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            await comm.save(out)
            print(f"  [{beat['beat']} / {emotion}] beat_{i:02d}.mp3  rate={rate} pitch={pitch}")
        except Exception as e:
            print(f"  [ERROR] beat_{i:02d} 생성 실패: {e}")
            raise


def generate_pangi_voice(script_path: str, output_dir: str):
    with open(script_path, encoding="utf-8") as f:
        data = json.load(f)
    beats = data.get("beats", [])
    asyncio.run(_generate_beats(beats, output_dir))


def _audio_duration(path: str) -> float:
    """ffprobe로 오디오 파일 실제 길이(초) 반환."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def measure_beat_durations(voice_dir: str, n_beats: int) -> list[float]:
    """beat_00.mp3 ~ beat_{n-1}.mp3 실제 길이(초) 목록 반환."""
    durations = []
    for i in range(n_beats):
        path = os.path.join(voice_dir, f"beat_{i:02d}.mp3")
        durations.append(_audio_duration(path))
    return durations


if __name__ == "__main__":
    generate_pangi_voice(
        script_path="tmp/aitheater/script.json",
        output_dir="tmp/aitheater/voice",
    )
