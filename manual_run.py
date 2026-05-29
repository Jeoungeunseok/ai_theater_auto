import os
import json
from scripts.generate_script import generate_pangi_script
from scripts.generate_voice import generate_pangi_voice
from scripts.generate_image import generate_background
from scripts.render_short import render_pangi_short


def main():
    # ── 에피소드 설정 ──────────────────────────────────────
    topic = "상사 몰래 쉬는 법"
    category = "직장"
    episode_no = 1

    tmp_dir = f"tmp/aitheater/ep{episode_no:02d}"
    os.makedirs(tmp_dir, exist_ok=True)

    # 1. 대본 생성
    print("── 1. 대본 생성 ──")
    script = generate_pangi_script(topic, category=category, episode_no=episode_no)
    script_path = os.path.join(tmp_dir, "script.json")
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)
    print(f"   저장: {script_path}")

    # 2. 배경 이미지 생성
    print("── 2. 배경 이미지 생성 ──")
    bg_path = f"assets/bg/ep{episode_no:02d}_{category}.webp"
    if not os.path.exists(bg_path):
        generate_background(topic, category=category, output_path=bg_path)
    else:
        print(f"   기존 배경 재사용: {bg_path}")

    # 3. 보이스 생성 (팡이 단일 화자)
    print("── 3. 팡이 보이스 생성 ──")
    voice_dir = os.path.join(tmp_dir, "voice")
    generate_pangi_voice(script_path, output_dir=voice_dir)

    # 4. 퍼펫 클립 조립 → 최종 영상
    print("── 4. 영상 렌더링 ──")
    output_path = os.path.join(tmp_dir, f"ep{episode_no:02d}_final.mp4")
    render_pangi_short(
        script_path=script_path,
        voice_dir=voice_dir,
        bg_path=bg_path,
        output_path=output_path,
        category=category,
    )

    print(f"\n완료! 영상: {output_path}")


if __name__ == "__main__":
    main()
