import base64
import os
import platform
import subprocess
import time
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI
from io import BytesIO

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import googleapiclient.discovery
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # 댓글 읽기용
]

_RETRIABLE_STATUS = {500, 502, 503, 504}
_CHUNK_SIZE = 5 * 1024 * 1024  # 5MB

_CATEGORY_TAGS = {
    "직장": ["직장인", "퇴근", "상사", "야근", "회사생활"],
    "욕망": ["욕망", "쇼핑", "음식", "게임", "미루기"],
    "부부": ["부부", "결혼", "집안일", "데이트", "육아"],
    "일상": ["일상", "월요병", "SNS", "건강", "이웃"],
}


# ── OAuth ─────────────────────────────────────────────────

def _build_credentials() -> Credentials | None:
    """YOUTUBE_REFRESH_TOKEN 기반 credentials 생성. Access token은 자동 갱신."""
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

    if not all([refresh_token, client_id, client_secret]):
        print("[WARN] YouTube OAuth 환경변수 미설정 (YOUTUBE_REFRESH_TOKEN 등)")
        return None

    creds = Credentials(
        token=None,  # google-auth가 refresh_token으로 자동 발급
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def get_youtube_client():
    creds = _build_credentials()
    if not creds:
        return None
    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)


# ── 메타데이터 ────────────────────────────────────────────

def build_tags(category: str) -> list[str]:
    base = ["팡이", "본심대변인", "Shorts", "숏폼", "공감", "한국어"]
    return base + _CATEGORY_TAGS.get(category, [])


# ── 썸네일 생성 ───────────────────────────────────────────

_CAT_CONTEXT = {
    "직장": "Korean office workplace",
    "욕망": "Korean daily life, temptation and desire",
    "부부": "Korean married couple at home",
    "일상": "Korean everyday life",
}


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


def _build_thumbnail_prompt(topic: str, category: str, hook_line: str) -> str:
    ctx = _CAT_CONTEXT.get(category, "Korean daily life")
    scene = hook_line[:60] if hook_line else topic
    return (
        f"YouTube Shorts thumbnail illustration: {ctx} setting. "
        f"Topic: '{topic}'. "
        f"Scene: {scene}. "
        f"Style: bright vibrant cartoon illustration, bold eye-catching composition, "
        f"comic style, funny and relatable. No text or letters anywhere in the image. "
        f"High contrast punchy colors, 16:9 wide shot framing."
    )


def _pillow_overlay(img: Image.Image, topic: str) -> Image.Image:
    """AI 이미지 위에 제목 텍스트 오버레이 — 반투명 하단 그라디언트 바."""
    W, H = 1280, 720
    img = img.resize((W, H), Image.LANCZOS)
    draw = ImageDraw.Draw(img, "RGBA")
    font_path = _font_path()

    try:
        title_font = ImageFont.truetype(font_path, 68) if font_path else ImageFont.load_default()
        sub_font   = ImageFont.truetype(font_path, 36) if font_path else ImageFont.load_default()
    except Exception:
        title_font = sub_font = ImageFont.load_default()

    # 하단 반투명 그라디언트 배경
    bar_h = 200
    overlay = Image.new("RGBA", (W, bar_h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for y in range(bar_h):
        alpha = int(180 * (y / bar_h))
        od.line([(0, y), (W, y)], fill=(10, 22, 48, alpha))
    img.paste(overlay, (0, H - bar_h), overlay)

    draw = ImageDraw.Draw(img)
    ACCENT = (123, 189, 212)
    YELLOW = (255, 235, 100)

    # 채널명 (하단 상단부)
    draw.text((50, H - 185), "팡이의 본심 대변인", font=sub_font, fill=ACCENT)

    # 주제 텍스트 (줄바꿈, 최대 2줄)
    max_chars = 13
    lines = [topic[i:i + max_chars] for i in range(0, min(len(topic), max_chars * 2), max_chars)]
    y = H - 148
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        draw.text((50, y), line, font=title_font, fill=YELLOW)
        y += 76

    # 상단 강조바
    draw.rectangle([0, 0, W, 10], fill=ACCENT)

    return img


def generate_thumbnail(
    topic: str,
    output_path: str,
    category: str = "일상",
    hook_line: str = "",
) -> bool:
    """gpt-image-2로 주제별 AI 썸네일 생성 + Pillow 텍스트 오버레이 (1280x720).

    THUMBNAIL_MODEL 환경변수 미설정 시 gpt-image-2 사용.
    FAL_KEY와 무관 — OpenAI 단독 호출.
    """
    model = os.getenv("THUMBNAIL_MODEL", "gpt-image-2")
    prompt = _build_thumbnail_prompt(topic, category, hook_line)

    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.images.generate(
            model=model,
            prompt=prompt,
            n=1,
            size="1024x1024",
            quality="medium",
        )
        img_bytes = base64.b64decode(resp.data[0].b64_json)
        img = Image.open(BytesIO(img_bytes)).convert("RGB")
        print(f"[thumb] gpt-image-2 생성 완료 — usage: {resp.usage}")
    except Exception as e:
        print(f"[thumb] AI 생성 실패 ({e}), Pillow 폴백")
        img = _pillow_fallback(topic)

    img = _pillow_overlay(img, topic)

    try:
        img.save(output_path, "JPEG", quality=92)
        return True
    except Exception as e:
        print(f"썸네일 저장 실패: {e}")
        return False


def _pillow_fallback(topic: str) -> Image.Image:
    """AI 생성 실패 시 단색 배경 폴백."""
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), (10, 22, 48))
    return img


# ── 업로드 ────────────────────────────────────────────────

def _start_caffeinate():
    """macOS 전용 — 업로드 중 슬립 차단."""
    if platform.system() != "Darwin":
        return None
    try:
        return subprocess.Popen(["caffeinate", "-dims"])
    except FileNotFoundError:
        return None


def _execute_resumable(insert_request) -> str | None:
    """청크 단위 업로드 + 지수 백오프 재시도."""
    MAX_RETRIES = 5
    response = None
    retry = 0

    while response is None:
        try:
            status, response = insert_request.next_chunk()
            if status:
                print(f"  업로드 {int(status.progress() * 100)}%")
            retry = 0  # 성공 시 재시도 카운터 리셋
        except HttpError as e:
            if e.resp.status in _RETRIABLE_STATUS and retry < MAX_RETRIES:
                wait = 2 ** retry
                print(f"  HTTP {e.resp.status} — {wait}초 후 재시도")
                time.sleep(wait)
                retry += 1
            else:
                raise

    video_id = response["id"]
    print(f"업로드 완료: https://youtu.be/{video_id}")
    return video_id


def upload_to_youtube(
    video_path: str,
    title: str,
    description: str,
    category: str = "일상",
    tags: list = None,
    thumbnail_path: str = None,
) -> str | None:
    """YouTube Resumable Upload + caffeinate + 썸네일 등록."""
    youtube = get_youtube_client()
    if not youtube:
        return None

    body = {
        "snippet": {
            "title": title[:100],  # YouTube 제목 100자 제한
            "description": description,
            "tags": tags or build_tags(category),
            "categoryId": "24",    # Entertainment
            "defaultLanguage": "ko",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=_CHUNK_SIZE,
    )
    insert_request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    caffeinate = _start_caffeinate()
    try:
        video_id = _execute_resumable(insert_request)
    finally:
        if caffeinate:
            caffeinate.terminate()

    if video_id and thumbnail_path and os.path.exists(thumbnail_path):
        _upload_thumbnail(youtube, video_id, thumbnail_path)

    return video_id


def _upload_thumbnail(youtube, video_id: str, thumbnail_path: str):
    try:
        with open(thumbnail_path, "rb") as f:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaIoBaseUpload(f, mimetype="image/jpeg"),
            ).execute()
        print(f"썸네일 등록 완료: {video_id}")
    except HttpError as e:
        print(f"썸네일 등록 실패: {e}")
