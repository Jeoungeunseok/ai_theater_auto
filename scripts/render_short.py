import json
import os
import platform
import subprocess
import yaml
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv()

_BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLIPS_DIR = os.getenv("PANGI_CLIPS_DIR",  "assets/pang/clips")
_EYES_DIR  = os.getenv("PANGI_EYES_DIR",   "assets/pang/eyes")
_BASE_BODY = os.getenv("PANGI_BODY",        "assets/pang/base/body_front.png")
_SFX_DIR   = os.getenv("PANGI_SFX_DIR",     "assets/sfx")

# v4 §2.6(2) 효과음(SFX) 맵 — 비트 타입별 비트 시작점에 자동 삽입.
# 파일이 존재할 때만 적용(없으면 무음 스킵).
_SFX_BY_BEAT = {
    "후킹":    "hook.wav",      # 시선 끄는 "확!"
    "본심수신": "signal.wav",    # 시그니처 신호음 "삐빅 📶"
    "전개1":   "tip.wav",       # 전개 첫 번째 등장 "딩!"
    "전개2":   None,            # 2·3번째는 무음 — 흐름 끊지 않게
    "전개3":   None,
    "마무리":   "punch.wav",     # 펀치라인·반전 임팩트 "쾅"
}
# 감정 오버라이드 — 젤리/멍함 허당 개그: 신호 끊김음 "띠로링~"
_SFX_BY_EMOTION = {
    "멍함":   "glitch.wav",
    "재부팅": "glitch.wav",
}

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

_CATEGORY_BG_COLOR = {
    "직장": (41,  57,  100),   # 네이비
    "욕망": (102, 51,  153),   # 퍼플
    "부부": (220, 100,  85),   # 코랄
    "일상": (80,  180, 160),   # 민트
}


def _black_bg(tmp_dir: str, category: str = "") -> str:
    """폴백용 단색 배경 이미지 생성 (Kling 클립 없는 beat에서만 사용)."""
    color = _CATEGORY_BG_COLOR.get(category, (30, 30, 30))
    path = os.path.join(tmp_dir, f"_fallback_bg_{category or 'default'}.png")
    if not os.path.exists(path):
        Image.new("RGB", (1080, 1920), color).save(path)
    return path

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
    """감정별 퍼펫 애니메이션 클립 경로. 없으면 None."""
    candidates = [
        os.path.join(_CLIPS_DIR, f"{emotion}.mov"),
        os.path.join(_CLIPS_DIR, "talk.mov"),
        os.path.join(_CLIPS_DIR, "idle.mov"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _expression_png(emotion: str) -> str | None:
    """크롭된 감정 PNG 경로. 없으면 None."""
    p = os.path.join(_EYES_DIR, f"{emotion}.png")
    return p if os.path.exists(p) else None


def _composite_character(bg_path: str, emotion: str, output_path: str):
    """
    배경 위에 팡이 캐릭터(표정 PNG)를 합성한 정적 이미지 생성.
    퍼펫 클립이 없을 때 사용하는 정적 표정 모드.
    """
    bg = Image.open(bg_path).convert("RGBA")
    bg = bg.resize((1080, 1920), Image.LANCZOS)

    expr_path = _expression_png(emotion)
    if not expr_path:
        # 표정 PNG도 없으면 배경만 반환
        bg.convert("RGB").save(output_path)
        return

    expr = Image.open(expr_path).convert("RGBA")

    # 캐릭터를 화면 너비의 65% 크기로 리사이즈
    char_w = int(1080 * 0.65)
    ratio = char_w / expr.width
    char_h = int(expr.height * ratio)
    expr = expr.resize((char_w, char_h), Image.LANCZOS)

    # 화면 하단 35% 지점에 캐릭터 중앙 배치
    x = (1080 - char_w) // 2
    y = int(1920 * 0.30)

    bg.paste(expr, (x, y), expr)
    bg.convert("RGB").save(output_path)


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
    output_path: str, style: dict = None, emotion: str = "평온",
):
    """
    퍼펫 클립 없을 때: 배경 + 정적 표정 PNG + TTS + 자막으로 렌더링.
    표정 PNG도 없으면 배경만 사용.
    """
    # 1. 배경 + 캐릭터 표정 합성
    composed = output_path.replace(".mp4", "_composed.png")
    _composite_character(bg_path, emotion, composed)

    # 2. 자막 합성
    captioned = output_path.replace(".mp4", "_sub.png")
    _burn_subtitle(composed, subtitle, captioned, style=style)
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
        for tmp in [composed, captioned]:
            if os.path.exists(tmp):
                os.remove(tmp)


# ── Kling 클립 렌더 (TTS + 자막 합성) ──────────────────────

def _render_beat_with_kling(
    clip_path: str, audio_path: str, subtitle: str,
    output_path: str, style: dict = None, duration_sec: int = None,
    emphasis: str = None,
):
    """
    Kling 생성 클립에 TTS 오디오 교체 + 자막 합성.
    클립이 beat보다 길면 duration_sec 기준으로 트림.
    v4 §2.6(3): emphasis 단어가 있으면 본 자막 위에 강조색·큰 글씨로 한 줄 더.
    """
    style = style or _DEFAULT_STYLE
    codec = _video_codec()
    font  = _font_path()
    font_escaped = font.replace(":", r"\:").replace("'", r"\'") if font else ""

    tc = style["text_color"]
    bc = style["border_color"]
    ac = style.get("accent_color", _DEFAULT_STYLE["accent_color"])
    text_hex   = f"#{tc[0]:02x}{tc[1]:02x}{tc[2]:02x}"
    border_hex = f"#{bc[0]:02x}{bc[1]:02x}{bc[2]:02x}"
    accent_hex = f"#{ac[0]:02x}{ac[1]:02x}{ac[2]:02x}"

    safe_sub = subtitle.replace("'", "\\'").replace(":", r"\:")[:40]
    drawtext = (
        f"drawtext=fontfile='{font_escaped}':text='{safe_sub}':"
        f"fontsize=44:fontcolor={text_hex}:borderw=3:bordercolor={border_hex}:"
        f"x=(w-text_w)/2:y=h*0.82"
        if font_escaped else ""
    )

    vf_parts = ["scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"]
    if drawtext:
        vf_parts.append(drawtext)
        if emphasis:
            safe_emph = emphasis.replace("'", "\\'").replace(":", r"\:")[:12]
            vf_parts.append(
                f"drawtext=fontfile='{font_escaped}':text='{safe_emph}':"
                f"fontsize=72:fontcolor={accent_hex}:borderw=4:bordercolor={border_hex}:"
                f"x=(w-text_w)/2:y=h*0.72"
            )
    vf = ",".join(vf_parts)

    cmd = [
        "ffmpeg", "-y",
        "-i", clip_path,    # Kling 영상
        "-i", audio_path,   # TTS 오디오
        "-map", "0:v",      # 영상은 Kling 것 사용
        "-map", "1:a",      # 오디오는 TTS로 교체
        "-vf", vf,
        "-c:v", codec[0], *codec[1:],
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
    ]
    if duration_sec:
        # TTS-FIRST: duration_sec = tts_sec + 0.4 → 0.4초 여유를 살리기 위해
        # -shortest 대신 -t 단독 사용 (오디오 끝 후 0.4초 영상이 묵음으로 남음)
        cmd += ["-t", str(duration_sec)]
    else:
        cmd += ["-shortest"]  # duration 미정 시 오디오 길이 기준
    cmd.append(output_path)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg 실패:\n{result.stderr}")


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


def _beat_sfx(beat_name: str, emotion: str) -> str | None:
    """비트/감정에 매핑된 SFX 경로. 감정 오버라이드 우선, 파일 없으면 None."""
    filename = _SFX_BY_EMOTION.get(emotion) or _SFX_BY_BEAT.get(beat_name)
    if not filename:  # None 명시 또는 키 없음 모두 처리
        return None
    path = os.path.join(_SFX_DIR, filename)
    return path if os.path.exists(path) else None


def _mix_sfx(video_path: str, sfx_path: str, volume: float = 0.6):
    """비트 시작점(t=0)에 SFX를 기존 오디오 위로 믹싱 (in-place)."""
    tmp = video_path.replace(".mp4", "_sfx.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", sfx_path,
        "-filter_complex",
        f"[1:a]volume={volume}[sfx];"
        f"[0:a][sfx]amix=inputs=2:duration=first:dropout_transition=0[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac",
        tmp,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        os.replace(tmp, video_path)
        print(f"    SFX 삽입: {os.path.basename(sfx_path)}")
    else:
        print(f"    [WARN] SFX 삽입 실패 — 원본 유지: {result.stderr[:100]}")
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
    output_path: str,
    category: str = "일상",
    bg_path: str = None,
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
        audio     = os.path.join(voice_dir, f"beat_{i:02d}.mp3")
        subtitle  = beat.get("dialogue", "")
        emphasis  = beat.get("emphasis", "")
        emotion   = beat.get("emotion", "평온")
        beat_name = beat.get("beat", "")
        duration  = beat.get("duration_sec")
        out       = os.path.join(tmp_dir, f"beat_{i:02d}.mp4")

        # Kling 클립이 있으면 최우선 사용
        kling_clip = os.path.join(voice_dir.replace("voice", "clips"), f"beat_{i:02d}.mp4")
        puppet     = _puppet_clip(beat_name, emotion)

        if os.path.exists(kling_clip):
            print(f"  [{beat_name}] Kling 클립 사용")
            _render_beat_with_kling(kling_clip, audio, subtitle, out,
                                    style=style, duration_sec=duration,
                                    emphasis=emphasis)
        elif puppet:
            resolved_bg = bg_path or _black_bg(tmp_dir, category)
            print(f"  [{beat_name}] 퍼펫 클립: {os.path.basename(puppet)}")
            _render_beat_with_puppet(resolved_bg, puppet, audio, subtitle, out, style=style)
        else:
            resolved_bg = bg_path or _black_bg(tmp_dir, category)
            has_expr = _expression_png(emotion) is not None
            mode = "정적 표정" if has_expr else "배경만"
            print(f"  [{beat_name}] 클립 없음 — {mode} 폴백 ({emotion})")
            _render_beat_fallback(resolved_bg, audio, subtitle, out, style=style, emotion=emotion)

        # v4 §2.6(2): 비트 시작점에 SFX 자동 삽입 (파일 있을 때만)
        sfx = _beat_sfx(beat_name, emotion)
        if sfx:
            _mix_sfx(out, sfx)

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
        output_path="tmp/aitheater/ep01_final.mp4",
        category="직장",
    )
