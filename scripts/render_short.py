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
            "/System/Library/Fonts/Supplemental/AppleSDGothicNeo.ttc",
            os.path.expanduser("~/Library/Fonts/NanumGothic.ttf"),
            "/Library/Fonts/NanumGothic.ttf",
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
    linux_font = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    if os.path.exists(linux_font):
        return linux_font
    return ""


def render_scene(audio_path: str, background_path: str, caption: str, output_path: str):
    """단일 장면 렌더링 (배경 이미지 + 오디오 + 자막).

    한글 자막은 text= 대신 textfile= 방식으로 처리하여 인코딩 깨짐 방지.
    """
    codec_args = _video_codec()
    font_path = _font_path()
    font_arg = f":fontfile='{font_path}'" if font_path else ""

    caption_file = output_path.replace(".mp4", "_cap.txt")
    with open(caption_file, "w", encoding="utf-8") as f:
        f.write(caption)

    command = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", background_path,
        "-i", audio_path,
        "-c:v", codec_args[0], *codec_args[1:],
        "-pix_fmt", "yuv420p",
        "-vf", (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            f"drawtext=textfile='{caption_file}'{font_arg}"
            ":fontcolor=white:fontsize=64"
            ":x=(w-text_w)/2:y=(h-text_h)*0.8"
            ":box=1:boxcolor=black@0.5:boxborderw=10"
        ),
        "-c:a", "aac",
        "-shortest",
        output_path,
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed:\n{result.stderr}")
    finally:
        if os.path.exists(caption_file):
            os.remove(caption_file)


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


def render_full_short(script_path: str, voice_dir: str, image_dir: str, output_path: str):
    """스크립트 JSON + 보이스 파일들 + 각 장면별 이미지 → 최종 쇼츠 mp4 1편 생성."""
    with open(script_path, encoding="utf-8") as f:
        data = json.load(f)

    tmp_dir = os.path.join(os.path.dirname(output_path), "scenes")
    os.makedirs(tmp_dir, exist_ok=True)

    scene_paths = []
    for i, scene in enumerate(data["scenes"]):
        audio = os.path.join(voice_dir, f"scene_{i:02d}.mp3")
        # 각 장면에 맞는 이미지 경로 (scene_00.png, scene_01.png ...)
        bg_image = os.path.join(image_dir, f"scene_{i:02d}.png")
        
        # 만약 해당 이미지가 없으면 기본 이미지나 첫 번째 이미지 사용 (예외 처리)
        if not os.path.exists(bg_image):
            bg_image = os.path.join(image_dir, "scene_00.png")

        scene_out = os.path.join(tmp_dir, f"scene_{i:02d}.mp4")
        render_scene(audio, bg_image, scene["caption"], scene_out)
        scene_paths.append(scene_out)
        print(f"  렌더링 완료: {scene_out}")

    concat_scenes(scene_paths, output_path)
    print(f"최종 영상 생성: {output_path}")


if __name__ == "__main__":
    render_full_short(
        script_path="tmp/aitheater/script_v1.json",
        voice_dir="tmp/aitheater/voice",
        image_dir="tmp/aitheater/images",
        output_path="tmp/aitheater/final.mp4",
    )
