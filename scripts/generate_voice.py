import json
import os
import re
import subprocess
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── 팡이 음성 설정 (mascot_coral_p5 고정) ──────────────────
_TTS_MODEL = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")
_TTS_VOICE = os.getenv("TTS_VOICE", "coral")
# 피치 +5반음, 속도 1.2배 → 얇고 빠른 마스코트 톤
_TTS_PITCH_SEMITONES = float(os.getenv("TTS_PITCH_SEMITONES", "5"))
_TTS_SPEED = float(os.getenv("TTS_SPEED", "1.2"))

_BASE_INSTRUCTION = (
    "아주 작고 귀여운 마스코트 캐릭터 목소리. 애교 가득, 콧소리 살짝 섞어서 "
    "통통 튀고 깜찍하게. 신나서 방방 뛰듯이 빠르고 밝게, 장난스럽게. "
    "물음표는 호기심 있게 끝을 올리고, 느낌표는 신나게 강조해줘."
)

# 감정별 추가 지시 — 마스코트 톤 위에 얹는 감정 뉘앙스
_EMOTION_INSTRUCT: dict[str, str] = {
    "평온":   "차분하고 편안한 느낌으로 또박또박.",
    "기쁨":   "활짝 웃으며 기쁘고 들뜬 목소리로.",
    "신남":   "엄청 신나고 텐션 최고로 들뜨게.",
    "설렘":   "두근두근 기대에 찬 설레는 목소리로.",
    "뿌듯함": "어깨 으쓱하며 뿌듯하고 자랑스럽게.",
    "자신감": "당당하고 확신에 찬 또렷한 톤으로.",
    "슬픔":   "시무룩하게 풀 죽은 목소리로, 살짝 느리게.",
    "분노":   "토라져서 뾰로통하게 살짝 화난 듯이.",
    "무서움": "겁먹고 조마조마한 떨리는 목소리로.",
    "충격":   "깜짝 놀라 눈 휘둥그레지듯 과장되게.",
    "심술":   "장난스럽고 짓궂게 약 올리듯이.",
    "멍함":   "넋 나간 듯 멍하고 느릿하게.",
    "과부하": "정신없이 버벅대며 과부하 걸린 듯 빠르게.",
    "재부팅": "차분하게 리셋되듯 또박또박.",
}


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


def _sample_rate(path: str) -> int:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "stream=sample_rate",
         "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    try:
        return int(result.stdout.strip())
    except (ValueError, AttributeError):
        return 24000


def _pitch_shift(src: str, dst: str):
    """피치 +N반음 올리고 속도는 _TTS_SPEED로 — 얇고 빠른 마스코트 톤."""
    sr = _sample_rate(src)
    factor = 2 ** (_TTS_PITCH_SEMITONES / 12)   # 피치 배율
    tempo = _TTS_SPEED / factor                  # asetrate가 올린 속도 보정 + 목표 속도
    # atempo는 0.5~2.0만 허용 — 범위 밖이면 체이닝
    tempo_chain = []
    t = tempo
    while t < 0.5:
        tempo_chain.append("atempo=0.5")
        t /= 0.5
    while t > 2.0:
        tempo_chain.append("atempo=2.0")
        t /= 2.0
    tempo_chain.append(f"atempo={t:.5f}")
    af = f"asetrate={sr}*{factor:.6f},aresample={sr}," + ",".join(tempo_chain)

    cmd = ["ffmpeg", "-y", "-i", src, "-af", af, dst]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not os.path.exists(dst):
        raise RuntimeError(f"피치 시프트 실패:\n{result.stderr}")


def _synthesize_beat(text: str, emotion: str, out_path: str):
    instructions = _BASE_INSTRUCTION + " " + _EMOTION_INSTRUCT.get(emotion, "")
    raw = out_path.replace(".mp3", "_raw.mp3")
    with _client.audio.speech.with_streaming_response.create(
        model=_TTS_MODEL,
        voice=_TTS_VOICE,
        input=text,
        instructions=instructions,
    ) as resp:
        resp.stream_to_file(raw)
    _pitch_shift(raw, out_path)
    os.remove(raw)


def _generate_beats(beats: list, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    for i, beat in enumerate(beats):
        emotion = beat.get("emotion", "평온")
        text = _clean(beat.get("dialogue", ""))
        out = os.path.join(output_dir, f"beat_{i:02d}.mp3")
        try:
            _synthesize_beat(text, emotion, out)
            print(f"  [{beat.get('beat','')} / {emotion}] beat_{i:02d}.mp3  "
                  f"({_TTS_VOICE}, +{_TTS_PITCH_SEMITONES}반음, {_TTS_SPEED}x)")
        except Exception as e:
            print(f"  [ERROR] beat_{i:02d} 생성 실패: {e}")
            raise


def generate_pangi_voice(script_path: str, output_dir: str):
    with open(script_path, encoding="utf-8") as f:
        data = json.load(f)
    beats = data.get("beats", [])
    _generate_beats(beats, output_dir)


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
