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
    ("ko-KR-SunHiNeural",              "+18%", "+8Hz"),
    ("ko-KR-InJoonNeural",             "+15%", "+0Hz"),
]


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
        voice, rate, pitch = voice_cfg

        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            await communicate.save(output_path)
            print(f"  Generated [{character}] scene_{i:02d}.mp3")
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
