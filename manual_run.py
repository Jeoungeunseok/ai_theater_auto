import asyncio
import os
import json
from scripts.generate_script import generate_short_script
from scripts.generate_voice import generate_voice_over
from scripts.fetch_assets import fetch_pexels_image
from scripts.render_short import render_full_short

async def main():
    topic = "흥부전 Ep.01 - 제비가 가져온 보물"
    tmp_dir = "tmp/aitheater"
    os.makedirs(tmp_dir, exist_ok=True)
    
    # 1. 대본 생성
    print("--- 1. Generating Script ---")
    script = generate_short_script(topic)
    script_path = os.path.join(tmp_dir, "script_v1.json")
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)
    
    # 2. 음성 생성
    print("--- 2. Generating Voice ---")
    voice_dir = os.path.join(tmp_dir, "voice")
    await generate_voice_over(script_path, voice_dir)
    
    # 3. 배경 이미지 수집 (첫 번째 장면 키워드로 하나만 가져오기 - 단순화)
    print("--- 3. Fetching Background ---")
    bg_path = "storage/bg_pool/background.jpg"
    os.makedirs("storage/bg_pool", exist_ok=True)
    fetch_pexels_image("traditional korean village", bg_path)
    
    # 4. 영상 렌더링
    print("--- 4. Rendering Video ---")
    output_video = os.path.join(tmp_dir, "final_shorts.mp4")
    render_full_short(script_path, voice_dir, bg_path, output_video)
    
    print(f"\n✨ Phase 1 Complete! Video saved at: {output_video}")

if __name__ == "__main__":
    asyncio.run(main())
