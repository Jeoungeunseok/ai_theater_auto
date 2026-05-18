import subprocess
import os
import json

def render_scene(audio_path, background_path, caption, output_path):
    """
    단일 장면을 렌더링합니다. (배경 이미지 + 오디오 + 자막)
    """
    # Apple Silicon VideoToolbox 가속 활용 (h264_videotoolbox)
    # 자막 위치 및 스타일링은 추가 개선 필요
    command = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", background_path,
        "-i", audio_path,
        "-c:v", "h264_videotoolbox",
        "-b:v", "4M",
        "-pix_fmt", "yuv420p",
        "-vf", f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,drawtext=text='{caption}':fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)*0.8:box=1:boxcolor=black@0.5:boxborderw=10",
        "-c:a", "aac",
        "-shortest",
        output_path
    ]
    
    subprocess.run(command, check=True)

if __name__ == "__main__":
    # 임시 테스트용 (실제 실행을 위해서는 background.jpg 등이 필요함)
    print("Render script initialized. Use render_scene function to combine assets.")
