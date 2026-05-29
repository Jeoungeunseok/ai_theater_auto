import asyncio
import json
import re
import edge_tts
import os

# 캐릭터별 목소리 배정 순서
# 나레이터: 차분한 남성 목소리
# 주인공(첫 번째 캐릭터): 밝고 에너지 있는 여성 목소리
# 조연(두 번째 캐릭터~): 남성 목소리
NARRATOR_VOICE = ("ko-KR-HyunsuMultilingualNeural", "+5%",  "+0Hz")
CHARACTER_VOICES = [
    ("ko-KR-SunHiNeural",  "+18%", "+8Hz"),
    ("ko-KR-InJoonNeural", "+15%", "+0Hz"),
]

# 감정별 rate/pitch 보정값 (캐릭터 기본값에 더해짐)
EMOTION_VOICE_MOD = {
    "평온":   (  0,  0),
    "기쁨":   ( +5, +3),
    "신남":   (+10, +5),
    "설렘":   ( +5, +5),
    "뿌듯함": ( +3, +2),
    "자신감": ( +5, +2),
    "슬픔":   (-10, -5),
    "분노":   (+10, -8),
    "무서움": ( -8, +5),
    "충격":   (+12, +8),
    "눈물":   (-12, -5),
    "심술":   ( +5, -5),
    "멍함":   (-15, -3),
    "과부하": (+15, +10),
    "재부팅": (  0,  0),
}


def _apply_emotion(base_rate: str, base_pitch: str, emotion: str):
    """기본 rate/pitch에 감정 보정값을 적용합니다."""
    mod_rate, mod_pitch = EMOTION_VOICE_MOD.get(emotion, (0, 0))

    # "+18%" → 18 파싱
    r = int(base_rate.replace("%", "").replace("+", ""))
    p = int(base_pitch.replace("Hz", "").replace("+", ""))

    final_rate  = f"{r + mod_rate:+d}%"
    final_pitch = f"{p + mod_pitch:+d}Hz"
    return final_rate, final_pitch


def _clean_for_tts(text: str) -> str:
    """TTS 전달 전 이모지·효과음·중복 구두점 제거."""
    emoji_pattern = re.compile(
        "[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0000FE00-\U0000FE0F]+",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub("", text)
    text = re.sub(r"\([^)]*(?:효과|소리|음)[^)]*\)", "", text)
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\?{2,}", "?", text)
    return text.strip()


def _build_voice_map(characters: dict) -> dict:
    """캐릭터 목록에서 이름 → (voice, rate, pitch) 매핑 생성."""
    voice_map = {}
    char_idx = 0
    for name in characters:
        if name == "나레이터":
            voice_map[name] = NARRATOR_VOICE
        else:
            voice_map[name] = CHARACTER_VOICES[char_idx % len(CHARACTER_VOICES)]
            char_idx += 1
    return voice_map


async def generate_voice_over(script_path, output_dir):
    with open(script_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    os.makedirs(output_dir, exist_ok=True)

    characters = data.get("characters", {})
    voice_map = _build_voice_map(characters)

    # 등장인물 목소리 매핑 출력
    for name, (v, r, p) in voice_map.items():
        print(f"  [{name}] → {v} (rate={r}, pitch={p})")

    for i, scene in enumerate(data["scenes"]):
        character = scene.get("character", "나레이터")
        # dialogue 필드 우선, 없으면 구버전 narration 폴백
        text = _clean_for_tts(scene.get("dialogue") or scene.get("narration", ""))
        output_path = os.path.join(output_dir, f"scene_{i:02d}.mp3")

        voice_cfg = voice_map.get(character, CHARACTER_VOICES[0])
        voice, base_rate, base_pitch = voice_cfg
        emotion = scene.get("emotion", "평온")
        rate, pitch = _apply_emotion(base_rate, base_pitch, emotion)

        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            await communicate.save(output_path)
            print(f"  Generated [{character} / {emotion}] scene_{i:02d}.mp3  (rate={rate}, pitch={pitch})")
        except Exception as e:
            print(f"  [ERROR] scene_{i:02d} 보이스 생성 실패: {e}")
            raise


if __name__ == "__main__":
    script_file = "tmp/aitheater/script_v1.json"
    audio_output = "tmp/aitheater/voice"
    if os.path.exists(script_file):
        asyncio.run(generate_voice_over(script_file, audio_output))
    else:
        print(f"Error: {script_file} not found.")
