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
    reference_image_paths = [
        f"storage/bg_pool/{series_name}_concept.png",
        f"storage/bg_pool/{series_name}_expressions.png",
    ]
    generate_images_for_script(
        script,
        image_dir,
        style=(
            "All characters MUST be based on 팡이(Pangi), the personified Wi-Fi character shown in the reference images. "
            "Use the 팡이 base design for every character. "
            "If a character is an animal, ADD that animal's features (wings, beak, ears, tail, stripes, etc.) onto the 팡이 body — do NOT draw a realistic animal. "
            "Korean folk tale 2D illustration, vibrant colors, cinematic lighting."
        ),
        reference_image_paths=reference_image_paths,
    )

    # 4. 영상 렌더링
    print("--- 4. Rendering Video ---")
    output_video = os.path.join(tmp_dir, "final_shorts.mp4")
    render_full_short(script_path, voice_dir, image_dir, output_video)

    print(f"\nDone! Video saved at: {output_video}")

if __name__ == "__main__":
    asyncio.run(main())
