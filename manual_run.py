import os
import json
from scripts.generate_script import generate_pangi_script
from scripts.generate_clips import generate_all_clips
from scripts.generate_voice import generate_pangi_voice
from scripts.render_short import render_pangi_short


def main():
    # ── 에피소드 설정 ──────────────────────────────────────
    topic      = "상사 몰래 쉬는 법"
    category   = "직장"
    episode_no = 1

    tmp_dir = f"tmp/aitheater/ep{episode_no:02d}"
    os.makedirs(tmp_dir, exist_ok=True)

    # 1. 대본 생성
    print("── 1. 대본 생성 ──")
    script = generate_pangi_script(topic, category=category, episode_no=episode_no)
    script_path = os.path.join(tmp_dir, "script.json")
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)
    for b in script.get("beats", []):
        print(f"   [{b['beat']}] {b['emotion']} — {b['dialogue'][:30]}...")

    # 2. Kling 클립 생성 (beat별 캐릭터 영상)
    print("\n── 2. Kling 클립 생성 ──")
    clips_dir = os.path.join(tmp_dir, "clips")
    generate_all_clips(script, clips_dir)

    # 3. TTS 보이스 생성
    print("\n── 3. 팡이 보이스 생성 ──")
    voice_dir = os.path.join(tmp_dir, "voice")
    generate_pangi_voice(script_path, output_dir=voice_dir)

    # 4. 렌더링 (Kling 클립 + TTS + 자막)
    print("\n── 4. 영상 렌더링 ──")
    output_path = os.path.join(tmp_dir, f"ep{episode_no:02d}_final.mp4")
    render_pangi_short(
        script_path=script_path,
        voice_dir=voice_dir,
        bg_path=None,       # Kling 클립이 있으면 배경 불필요
        output_path=output_path,
        category=category,
    )

    print(f"\n완료! 영상: {output_path}")


if __name__ == "__main__":
    main()
