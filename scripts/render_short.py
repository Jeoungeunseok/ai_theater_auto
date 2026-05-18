import subprocess
import os
import json
import platform


def _video_codec():
    """macOS는 VideoToolbox 하드웨어 가속, Linux(Docker)는 libx264 소프트웨어."""
    if platform.system() == "Darwin":
        return ["h264_videotoolbox", "-b:v", "4M"]
    return ["libx264", "-crf", "23", "-preset", "fast"]


def _font_path() -> str:
    """환경별 한글 폰트 경로 반환."""
    if platform.system() == "Darwin":
        candidates = [
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
    # Linux(Docker): fonts-noto-cjk 설치 경로
    linux_font = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    if os.path.exists(linux_font):
        return linux_font
    return ""  # 폰트 못 찾으면 FFmpeg 기본값 사용


def _escape_drawtext(text: str) -> str:
    """FFmpeg drawtext 필터에서 깨지는 문자 이스케이프."""
    return text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")


def render_scene(audio_path: str, background_path: str, caption: str, output_path: str):
    """단일 장면 렌더링 (배경 이미지 + 오디오 + 자막)."""
    codec_args = _video_codec()
    escaped = _escape_drawtext(caption)
    font_path = _font_path()
    font_arg = f":fontfile='{font_path}'" if font_path else ""

    command = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", background_path,
        "-i", audio_path,
        "-c:v", codec_args[0], *codec_args[1:],
        "-pix_fmt", "yuv420p",
        "-vf", (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            f"drawtext=text='{escaped}'{font_arg}"
            ":fontcolor=white:fontsize=64"
            ":x=(w-text_w)/2:y=(h-text_h)*0.8"
            ":box=1:boxcolor=black@0.5:boxborderw=10"
        ),
        "-c:a", "aac",
        "-shortest",
        output_path,
    ]

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed:\n{result.stderr}")


def concat_scenes(scene_paths: list[str], output_path: str):
    """여러 장면 mp4를 순서대로 이어붙여 최종 쇼츠 영상 생성."""
    list_file = output_path.replace(".mp4", "_concat_list.txt")
    with open(list_file, "w") as f:
        for path in scene_paths:
            f.write(f"file '{os.path.abspath(path)}'\n")

    command = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        output_path,
    ]

    result = subprocess.run(command, capture_output=True, text=True)
    os.remove(list_file)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed:\n{result.stderr}")


def render_full_short(script_path: str, voice_dir: str, background_path: str, output_path: str):
    """스크립트 JSON + 보이스 파일들 + 배경 → 최종 쇼츠 mp4 1편 생성."""
    with open(script_path, encoding="utf-8") as f:
        data = json.load(f)

    tmp_dir = os.path.join(os.path.dirname(output_path), "scenes")
    os.makedirs(tmp_dir, exist_ok=True)

    scene_paths = []
    for i, scene in enumerate(data["scenes"]):
        audio = os.path.join(voice_dir, f"scene_{i:02d}.mp3")
        scene_out = os.path.join(tmp_dir, f"scene_{i:02d}.mp4")
        render_scene(audio, background_path, scene["caption"], scene_out)
        scene_paths.append(scene_out)
        print(f"  렌더링 완료: {scene_out}")

    concat_scenes(scene_paths, output_path)
    print(f"최종 영상 생성: {output_path}")


if __name__ == "__main__":
    render_full_short(
        script_path="tmp/aitheater/script_v1.json",
        voice_dir="tmp/aitheater/voice",
        background_path="storage/bg_pool/background.jpg",
        output_path="tmp/aitheater/final.mp4",
    )
