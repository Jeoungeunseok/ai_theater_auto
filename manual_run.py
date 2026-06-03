import os
import json
from scripts.generate_script import generate_pangi_script
from scripts.generate_clips import generate_all_clips
from scripts.generate_voice import generate_pangi_voice, measure_beat_durations
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

    # 2. TTS 보이스 생성 (v5 §2.1: TTS-FIRST — 길이를 먼저 확정)
    print("\n── 2. 팡이 보이스 생성 ──")
    voice_dir = os.path.join(tmp_dir, "voice")
    generate_pangi_voice(script_path, output_dir=voice_dir)

    # 3. TTS 길이 측정 → beat별 duration_sec 업데이트 (tts + 0.4s 여유)
    print("\n── 3. TTS 길이 측정 ──")
    n_beats = len(script["beats"])
    tts_durations = measure_beat_durations(voice_dir, n_beats)
    for i, beat in enumerate(script["beats"]):
        tts_sec = tts_durations[i]
        beat["tts_sec"] = round(tts_sec, 3)
        beat["duration_sec"] = round(tts_sec + 0.4, 3)  # 렌더 트림 기준
        print(f"   beat_{i:02d} TTS={tts_sec:.2f}s → Kling {'5s' if tts_sec <= 4.5 else '10s'} → trim={beat['duration_sec']}s")
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    # 4. Kling 클립 생성 (TTS 길이 기반 5s/10s 결정, generate_audio=false 무음)
    print("\n── 4. Kling 클립 생성 ──")
    clips_dir = os.path.join(tmp_dir, "clips")
    generate_all_clips(script, clips_dir, tts_durations=tts_durations)

    # 5. 렌더링 (Kling 클립 + TTS + 자막, duration_sec 기준 트림)
    print("\n── 5. 영상 렌더링 ──")
    output_path = os.path.join(tmp_dir, f"ep{episode_no:02d}_final.mp4")
    render_pangi_short(
        script_path=script_path,
        voice_dir=voice_dir,
        output_path=output_path,
        category=category,
        bg_path=None,
    )

    print(f"\n완료! 영상: {output_path}")


if __name__ == "__main__":
    main()
