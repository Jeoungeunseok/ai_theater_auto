import subprocess
import os
import json
import base64
import platform
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
_openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


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


def _burn_caption(image_path: str, caption: str, output_path: str):
    """Pillow로 이미지에 자막을 합성합니다."""
    font_path = _font_path()
    img = Image.open(image_path).convert("RGBA")
    w, h = img.size

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_size = max(36, w // 20)
    try:
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    max_chars = 16
    lines = [caption[i:i + max_chars] for i in range(0, len(caption), max_chars)]

    line_height = font_size + 12
    text_y = int(h * 0.78)
    padding = 14

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (w - text_w) // 2
        y = text_y + i * line_height
        draw.rectangle(
            [x - padding, y - padding, x + text_w + padding, y + text_h + padding],
            fill=(0, 0, 0, 150),
        )
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

    combined = Image.alpha_composite(img, overlay).convert("RGB")
    combined.save(output_path)


def _draw_wifi_signal(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple):
    """팡이 상징인 와이파이 신호 아크를 장식으로 그립니다."""
    for i in range(3):
        r = size - i * (size // 4)
        bbox = [cx - r, cy - r, cx + r, cy + r]
        draw.arc(bbox, start=210, end=330, fill=color, width=max(4, size // 10))


def _create_choice_card(choices: list, output_path: str):
    """팡이 컨셉아트 스타일의 선택지 카드 이미지를 생성합니다."""
    w, h = 1080, 1920

    # 팡이 컬러 팔레트
    BG_COLOR      = (10, 22, 48)       # 딥 네이비
    PANGI_BLUE    = (123, 189, 212)    # 팡이 스카이블루
    BTN_A_COLOR   = (80, 160, 220)     # A버튼 블루
    BTN_B_COLOR   = (255, 140, 80)     # B버튼 코랄
    TITLE_COLOR   = (255, 235, 100)    # 노란 강조
    WHITE         = (255, 255, 255)
    CARD_BG       = (20, 40, 75)       # 카드 배경

    img = Image.new("RGB", (w, h), BG_COLOR)
    draw = ImageDraw.Draw(img)
    font_path = _font_path()

    try:
        title_font  = ImageFont.truetype(font_path, 68) if font_path else ImageFont.load_default()
        choice_font = ImageFont.truetype(font_path, 48) if font_path else ImageFont.load_default()
        label_font  = ImageFont.truetype(font_path, 72) if font_path else ImageFont.load_default()
    except Exception:
        title_font = choice_font = label_font = ImageFont.load_default()

    # 와이파이 장식 (상단 좌우)
    _draw_wifi_signal(draw, cx=160,     cy=340, size=90,  color=(*PANGI_BLUE, 120))
    _draw_wifi_signal(draw, cx=w - 160, cy=340, size=90,  color=(*PANGI_BLUE, 120))

    # 카드 배경 패널
    margin = 60
    draw.rounded_rectangle([margin, int(h * 0.22), w - margin, int(h * 0.82)],
                            radius=40, fill=CARD_BG)

    # 팡이 블루 상단 강조바
    draw.rounded_rectangle([margin, int(h * 0.22), w - margin, int(h * 0.22) + 10],
                            radius=8, fill=PANGI_BLUE)

    # 제목
    title = "여러분의 선택은?"
    bbox = draw.textbbox((0, 0), title, font=title_font)
    draw.text(((w - (bbox[2] - bbox[0])) // 2, int(h * 0.26)),
              title, font=title_font, fill=TITLE_COLOR)

    # A / B 버튼
    btn_cfg = [
        ("A", BTN_A_COLOR, int(h * 0.42)),
        ("B", BTN_B_COLOR, int(h * 0.60)),
    ]

    for (label, color, by1), choice in zip(btn_cfg, choices[:2]):
        by2 = by1 + 200
        draw.rounded_rectangle([margin + 20, by1, w - margin - 20, by2],
                                radius=28, fill=color)

        # 레이블 배지 (어두운 반원형 배경)
        badge_r = 44
        bx = margin + 20 + 28
        badge_y = by1 + (200 - badge_r * 2) // 2
        draw.ellipse([bx, badge_y, bx + badge_r * 2, badge_y + badge_r * 2],
                     fill=(0, 0, 0, 80) if False else (20, 40, 75))
        lb = draw.textbbox((0, 0), label, font=label_font)
        draw.text(
            (bx + (badge_r * 2 - (lb[2] - lb[0])) // 2,
             badge_y + (badge_r * 2 - (lb[3] - lb[1])) // 2 - 4),
            label, font=label_font, fill=WHITE
        )

        # 선택지 텍스트 (3줄까지 허용)
        max_chars = 13
        lines = [choice[j:j + max_chars] for j in range(0, len(choice), max_chars)]
        text_x = margin + 20 + badge_r * 2 + 30
        text_y_start = by1 + (200 - len(lines[:3]) * 54) // 2
        for k, line in enumerate(lines[:3]):
            draw.text((text_x, text_y_start + k * 54), line, font=choice_font, fill=WHITE)

    # 하단 힌트 문구
    hint = "댓글로 투표하세요!"
    hb = draw.textbbox((0, 0), hint, font=choice_font)
    draw.text(((w - (hb[2] - hb[0])) // 2, int(h * 0.84)),
              hint, font=choice_font, fill=PANGI_BLUE)

    img.save(output_path)


def render_scene(audio_path: str, background_path: str, caption: str, output_path: str):
    """단일 장면 렌더링 (배경 이미지 + 오디오 + 자막)."""
    codec_args = _video_codec()
    captioned_image = output_path.replace(".mp4", "_captioned.png")
    _burn_caption(background_path, caption, captioned_image)

    try:
        command = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", captioned_image,
            "-i", audio_path,
            "-c:v", codec_args[0], *codec_args[1:],
            "-pix_fmt", "yuv420p",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-c:a", "aac",
            "-shortest",
            output_path,
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed:\n{result.stderr}")
    finally:
        if os.path.exists(captioned_image):
            os.remove(captioned_image)


CHOICE_GUIDE_PATH = "storage/bg_pool/folktale_choice.png"


def _generate_choice_card_image(choices: list, output_path: str):
    """gpt-image-2로 가이드 이미지 스타일의 선택지 카드를 생성합니다."""
    guide_path = CHOICE_GUIDE_PATH

    if not os.path.exists(guide_path):
        # 가이드 이미지 없으면 Pillow 폴백
        _create_choice_card(choices, output_path)
        return

    choice_a = choices[0] if len(choices) > 0 else "선택지 A"
    choice_b = choices[1] if len(choices) > 1 else "선택지 B"

    prompt = (
        f"Create a choice card in exactly the same style as the reference image. "
        f"Keep the same layout, character (팡이, personified Wi-Fi), background, and visual design. "
        f"Change only the text: "
        f"Button A text: '{choice_a}' "
        f"Button B text: '{choice_b}' "
        f"Title: '여러분의 선택은?' "
        f"Bottom button: '댓글로 투표하세요!' "
        f"All text must be in Korean. Vertical 9:16 format."
    )

    try:
        with open(guide_path, "rb") as f:
            response = _openai_client.images.edit(
                model="gpt-image-2",
                image=f,
                prompt=prompt,
                size="1024x1536",
                n=1,
            )
        image_data = base64.b64decode(response.data[0].b64_json)
        with open(output_path, "wb") as f:
            f.write(image_data)
        print(f"  선택지 카드 생성 완료: {output_path}")
    except Exception as e:
        print(f"  [WARN] gpt-image-2 선택지 카드 생성 실패, Pillow 폴백: {e}")
        _create_choice_card(choices, output_path)


def render_choice_scene(choices: list, output_path: str, duration: int = 5):
    """선택지 카드를 5초짜리 무음 mp4로 렌더링합니다."""
    codec_args = _video_codec()
    card_path = output_path.replace(".mp4", "_card.png")
    _generate_choice_card_image(choices, card_path)

    try:
        command = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", card_path,
            "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-c:v", codec_args[0], *codec_args[1:],
            "-pix_fmt", "yuv420p",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-c:a", "aac",
            "-t", str(duration),
            output_path,
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed:\n{result.stderr}")
    finally:
        if os.path.exists(card_path):
            os.remove(card_path)


def concat_scenes(scene_paths: list, output_path: str):
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

    # 스토리 장면 렌더링
    for i, scene in enumerate(data["scenes"]):
        audio = os.path.join(voice_dir, f"scene_{i:02d}.mp3")
        bg_image = os.path.join(image_dir, f"scene_{i:02d}.png")
        if not os.path.exists(bg_image):
            bg_image = os.path.join(image_dir, "scene_00.png")

        # 자막은 실제 대사로 표시
        subtitle = scene.get("dialogue") or scene.get("narration", "")

        scene_out = os.path.join(tmp_dir, f"scene_{i:02d}.mp4")
        render_scene(audio, bg_image, subtitle, scene_out)
        scene_paths.append(scene_out)
        print(f"  렌더링 완료: {scene_out}")

    # 선택지 화면 렌더링
    choices = data.get("choices", [])
    if choices:
        choice_out = os.path.join(tmp_dir, "scene_choice.mp4")
        render_choice_scene(choices, choice_out)
        scene_paths.append(choice_out)
        print(f"  선택지 화면 렌더링 완료: {choice_out}")

    concat_scenes(scene_paths, output_path)
    print(f"최종 영상 생성: {output_path}")


if __name__ == "__main__":
    render_full_short(
        script_path="tmp/aitheater/script_v1.json",
        voice_dir="tmp/aitheater/voice",
        image_dir="tmp/aitheater/images",
        output_path="tmp/aitheater/final.mp4",
    )
