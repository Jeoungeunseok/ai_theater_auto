import asyncio
import json
import re
import edge_tts
import os


def _clean_for_tts(text: str) -> str:
    """TTS 전달 전 이모지·효과음·중복 구두점 제거."""
    # 이모지 제거
    emoji_pattern = re.compile(
        "[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0000FE00-\U0000FE0F]+",
        flags=re.UNICODE,
    )
    text = emoji_pattern.sub("", text)
    # 괄호 안 효과음 제거 (예: (효과음), (소리))
    text = re.sub(r"\([^)]*(?:효과|소리|음)[^)]*\)", "", text)
    # 연속 느낌표·물음표 정리
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\?{2,}", "?", text)
    return text.strip()


# AI 햄스터 영상 스타일: 밝고 빠른 에너지감
VOICE     = os.getenv("TTS_VOICE", "ko-KR-HyunsuMultilingualNeural")
TTS_RATE  = os.getenv("TTS_RATE",  "+18%")   # 속도 (빠를수록 에너지감 ↑)
TTS_PITCH = os.getenv("TTS_PITCH", "+8Hz")   # 음높이 (높을수록 밝고 귀여운 느낌)


async def generate_voice_over(script_path, output_dir):
    with open(script_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    os.makedirs(output_dir, exist_ok=True)

    for i, scene in enumerate(data["scenes"]):
        text = _clean_for_tts(scene["narration"])
        output_path = os.path.join(output_dir, f"scene_{i:02d}.mp3")
        try:
            communicate = edge_tts.Communicate(text, VOICE, rate=TTS_RATE, pitch=TTS_PITCH)
            await communicate.save(output_path)
            print(f"Generated voice: {output_path}")
        except Exception as e:
            print(f"[ERROR] scene_{i:02d} 보이스 생성 실패: {e}")
            raise


if __name__ == "__main__":
    script_file = "tmp/aitheater/script_v1.json"
    audio_output = "tmp/aitheater/voice"
    if os.path.exists(script_file):
        asyncio.run(generate_voice_over(script_file, audio_output))
    else:
        print(f"Error: {script_file} not found. Run generate_script.py first.")
