import asyncio
import json
import edge_tts
import os

async def generate_voice_over(script_path, output_dir):
    with open(script_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    os.makedirs(output_dir, exist_ok=True)
    
    for i, scene in enumerate(data['scenes']):
        text = scene['narration']
        # ko-KR-SunHiNeural 또는 ko-KR-InJoonNeural 추천
        communicate = edge_tts.Communicate(text, "ko-KR-SunHiNeural")
        output_path = os.path.join(output_dir, f"scene_{i:02d}.mp3")
        await communicate.save(output_path)
        print(f"Generated voice: {output_path}")

if __name__ == "__main__":
    script_file = "tmp/aitheater/script_v1.json"
    audio_output = "tmp/aitheater/voice"
    if os.path.exists(script_file):
        asyncio.run(generate_voice_over(script_file, audio_output))
    else:
        print(f"Error: {script_file} not found. Run generate_script.py first.")
