import asyncio
import os
import json
from scripts.generate_script import generate_short_script
from scripts.generate_voice import generate_voice_over
from scripts.generate_image import generate_images_for_script
from scripts.render_short import render_full_short

async def main():
    topic = "흥부전 Ep.01 - 제비가 가져온 보물"
    series_name = "folktale"
    tmp_dir = "tmp/aitheater"
    os.makedirs(tmp_dir, exist_ok=True)

    # 1. 대본 생성
    print("--- 1. Generating Script ---")
    script = generate_short_script(topic, series_name=series_name)
    script_path = os.path.join(tmp_dir, "script_v1.json")
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    # 2. 음성 생성
    print("--- 2. Generating Voice ---")
    voice_dir = os.path.join(tmp_dir, "voice")
    await generate_voice_over(script_path, voice_dir)

    # 3. 장면별 이미지 생성 (gpt-image-2)
    print("--- 3. Generating Images ---")
    image_dir = os.path.join(tmp_dir, "images")
    reference_image_path = f"storage/bg_pool/{series_name}_concept.webp"
    generate_images_for_script(
        script,
        image_dir,
        style="Korean folk tale illustration style, 2D, vibrant colors, cinematic lighting",
        reference_image_path=reference_image_path,
    )

    # 4. 영상 렌더링
    print("--- 4. Rendering Video ---")
    output_video = os.path.join(tmp_dir, "final_shorts.mp4")
    render_full_short(script_path, voice_dir, image_dir, output_video)

    print(f"\nDone! Video saved at: {output_video}")

if __name__ == "__main__":
    asyncio.run(main())
