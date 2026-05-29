import json
import os
import platform
import subprocess
import yaml
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv()

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLIPS_DIR = os.getenv("PANGI_CLIPS_DIR", "assets/pang/clips")

_CATEGORY_FILE = {
    "직장": "work.yaml",
    "욕망": "desire.yaml",
    "부부": "couple.yaml",
    "일상": "daily.yaml",
}

_DEFAULT_STYLE = {
    "bg_color": [0, 0, 0],
    "text_color": [255, 255, 255],
    "accent_color": [123, 189, 212],
    "border_color": [0, 0, 0],
}


# ── 카테고리 스타일 로드 ──────────────────────────────────

def _load_category_cfg(category: str) -> dict:
    filename = _CATEGORY_FILE.get(category)
    if not filename:
        return {}
    path = os.path.join(_BASE_DIR, "prompts", filename)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _subtitle_style(category: str) -> dict:
    cfg = _load_category_cfg(category)
    return cfg.get("subtitle_style", _DEFAULT_STYLE)


def _bgm_path(category: str) -> str | None:
    cfg = _load_category_cfg(category)
    p = cfg.get("bgm", "")
    return p if p and os.path.exists(p) else None


def _intro_path(category: str) -> str | None:
    cfg = _load_category_cfg(category)
    p = cfg.get("intro_clip", "")
    return p if p and os.path.exists(p) else None


# ── 공통 유틸 ─────────────────────────────────────────────

def _video_codec() -> list[str]:
    if platform.system() == "Darwin":
        return ["h264_videotoolbox", "-b:v", "4M"]
    return ["libx264", "-crf", "23", "-preset", "fast"]


def _font_path() -> str:
    if platform.system() == "Darwin":
        for p in [
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/System/Library/Fonts/Supplemental/AppleSDGothicNeo.ttc",
            os.path.expanduser("~/Library/Fonts/NanumGothic.ttf"),
        ]:
            if os.path.exists(p):
                return p
    linux = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    return linux if os.path.exists(linux) else ""


def _puppet_clip(beat_name: str, emotion: str) -> str | None:
    candidates = [
        os.path.join(_CLIPS_DIR, f"{emotion}.mov"),
        os.path.join(_CLIPS_DIR, "talk.mov"),
        os.path.join(_CLIPS_DIR, "idle.mov"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


# ── 자막 합성 (Pillow — 폴백용) ──────────────────────────

def _burn_subtitle(image_path: str, text: str, output_path: str, style: dict = None):
    style = style or _DEFAULT_STYLE
    bg_color = tuple(style["bg_color"]) + (160,)
    text_color = tuple(style["text_color"]) + (255,)

    font_path = _font_path()
    img = Image.open(image_path).convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_size = max(40, w // 18)
    try:
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    max_chars = 15
    lines = [text[i:i + max_chars] for i in range(0, len(text), max_chars)]
    line_h = font_size + 14
    y0 = int(h * 0.80)
    pad = 14

    for k, line in enumerate(lines[:3]):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (w - tw) // 2
        y = y0 + k * line_h
        draw.rectangle([x - pad, y - pad, x + tw + pad, y + th + pad], fill=bg_color)
        draw.text((x, y), line, font=font, fill=text_color)

    Image.alpha_composite(img, overlay).convert("RGB").save(output_path)


# ── beat 렌더링 ───────────────────────────────────────────

def _render_beat_with_puppet(
    bg_path: str, clip_path: str, audio_path: str,
    subtitle: str, output_path: str, style: dict = None,
):
    """배경 + 팡이 퍼펫 클립 + TTS + 자막 → beat mp4."""
    style = style or _DEFAULT_STYLE
    codec = _video_codec()
    font = _font_path()
    font_escaped = font.replace(":", r"\:").replace("'", r"\'") if font else ""

    tc = style["text_color"]
    bc = style["border_color"]
    text_color_hex = f"#{tc[0]:02x}{tc[1]:02x}{tc[2]:02x}"
    border_color_hex = f"#{bc[0]:02x}{bc[1]:02x}{bc[2]:02x}"

    safe_sub = subtitle.replace("'", "\\'").replace(":", r"\:")[:40]
    drawtext = (
        f"drawtext=fontfile='{font_escaped}':text='{safe_sub}':"
        f"fontsize=44:fontcolor={text_color_hex}:borderw=3:bordercolor={border_color_hex}:"
        f"x=(w-text_w)/2:y=h*0.80"
        if font_escaped else ""
    )

    filter_parts = [
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[bg]",
        "[1:v]format=rgba,scale=540:-1[puppet]",
        "[bg][puppet]overlay=x=(W-w)/2:y=H*0.25[v]",
    ]
    if drawtext:
        filter_parts.append(f"[v]{drawtext}[vt]")
        vmap = "[vt]"
    else:
        vmap = "[v]"

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", bg_path,
        "-stream_loop", "-1", "-i", clip_path,
        "-i", audio_path,
        "-filter_complex", ";".join(filter_parts),
        "-map", vmap, "-map", "2:a",
        "-c:v", codec[0], *codec[1:],
        "-c:a", "aac", "-pix_fmt", "yuv420p", "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg 실패:\n{result.stderr}")


def _render_beat_fallback(
    bg_path: str, audio_path: str, subtitle: str,
    output_path: str, style: dict = None,
):
    """퍼펫 클립 없을 때: 배경 + TTS + 자막만으로 렌더링."""
    captioned = output_path.replace(".mp4", "_sub.png")
    _burn_subtitle(bg_path, subtitle, captioned, style=style)
    codec = _video_codec()

    try:
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", captioned,
            "-i", audio_path,
            "-c:v", codec[0], *codec[1:],
            "-pix_fmt", "yuv420p",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-c:a", "aac", "-shortest",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg 실패:\n{result.stderr}")
    finally:
        if os.path.exists(captioned):
            os.remove(captioned)


# ── concat / BGM / 인트로 ────────────────────────────────

def _concat(scene_paths: list[str], output_path: str):
    list_file = output_path.replace(".mp4", "_list.txt")
    with open(list_file, "w") as f:
        for p in scene_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", output_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    os.remove(list_file)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat 실패:\n{result.stderr}")


def _mix_bgm(video_path: str, bgm_path: str):
    """BGM을 TTS 오디오에 낮은 볼륨으로 믹싱 (in-place)."""
    tmp = video_path.replace(".mp4", "_bgm.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-stream_loop", "-1", "-i", bgm_path,
        "-filter_complex",
        "[0:a]volume=1.0[voice];[1:a]volume=0.12[bgm];[voice][bgm]amix=inputs=2:duration=first[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-shortest",
        tmp,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        os.replace(tmp, video_path)
        print(f"  BGM 믹싱 완료")
    else:
        print(f"  [WARN] BGM 믹싱 실패 — 원본 유지: {result.stderr[:100]}")
        if os.path.exists(tmp):
            os.remove(tmp)


def _prepend_intro(video_path: str, intro_path: str):
    """인트로 클립을 영상 앞에 삽입 (in-place)."""
    tmp = video_path.replace(".mp4", "_with_intro.mp4")
    list_file = video_path.replace(".mp4", "_intro_list.txt")
    with open(list_file, "w") as f:
        f.write(f"file '{os.path.abspath(intro_path)}'\n")
        f.write(f"file '{os.path.abspath(video_path)}'\n")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", tmp]
    result = subprocess.run(cmd, capture_output=True, text=True)
    os.remove(list_file)
    if result.returncode == 0:
        os.replace(tmp, video_path)
        print(f"  인트로 삽입 완료")
    else:
        print(f"  [WARN] 인트로 삽입 실패 — 원본 유지")
        if os.path.exists(tmp):
            os.remove(tmp)


# ── 메인 렌더 함수 ────────────────────────────────────────

def render_pangi_short(
    script_path: str,
    voice_dir: str,
    bg_path: str,
    output_path: str,
    category: str = "일상",
):
    """팡이 에피소드 1편 렌더링: 퍼펫 클립 조립 → BGM → 인트로 → 최종 쇼츠 mp4."""
    with open(script_path, encoding="utf-8") as f:
        data = json.load(f)

    category = data.get("category", category)
    style = _subtitle_style(category)
    beats = data.get("beats", [])
    tmp_dir = os.path.join(os.path.dirname(output_path), "beats")
    os.makedirs(tmp_dir, exist_ok=True)

    beat_paths = []
    for i, beat in enumerate(beats):
        audio = os.path.join(voice_dir, f"beat_{i:02d}.mp3")
        subtitle = beat.get("dialogue", "")
        emotion = beat.get("emotion", "평온")
        beat_name = beat.get("beat", "")
        out = os.path.join(tmp_dir, f"beat_{i:02d}.mp4")

        clip = _puppet_clip(beat_name, emotion)
        if clip:
            print(f"  [{beat_name}] 퍼펫 클립: {os.path.basename(clip)}")
            _render_beat_with_puppet(bg_path, clip, audio, subtitle, out, style=style)
        else:
            print(f"  [{beat_name}] 퍼펫 클립 없음 — 정적 폴백")
            _render_beat_fallback(bg_path, audio, subtitle, out, style=style)

        beat_paths.append(out)
        print(f"    → {out}")

    _concat(beat_paths, output_path)

    # BGM 믹싱 (파일 있을 때만)
    bgm = _bgm_path(category)
    if bgm:
        _mix_bgm(output_path, bgm)

    # 인트로 삽입 (파일 있을 때만)
    intro = _intro_path(category)
    if intro:
        _prepend_intro(output_path, intro)

    print(f"\n최종 영상: {output_path}")


if __name__ == "__main__":
    render_pangi_short(
        script_path="tmp/aitheater/script.json",
        voice_dir="tmp/aitheater/voice",
        bg_path="assets/bg/ep01_workplace.webp",
        output_path="tmp/aitheater/ep01_final.mp4",
        category="직장",
    )
