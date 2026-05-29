import os
import platform
import subprocess
import time
from PIL import Image, ImageDraw, ImageFont

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


# ── 썸네일 생성 (Pillow) ──────────────────────────────────

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


def generate_thumbnail(topic: str, output_path: str) -> bool:
    """팡이 테마 썸네일 생성 (1280x720)."""
    W, H = 1280, 720
    BG = (10, 22, 48)       # 딥 네이비
    ACCENT = (123, 189, 212) # 팡이 스카이블루
    YELLOW = (255, 235, 100)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    font_path = _font_path()

    try:
        big_font = ImageFont.truetype(font_path, 80) if font_path else ImageFont.load_default()
        sub_font = ImageFont.truetype(font_path, 44) if font_path else ImageFont.load_default()
    except Exception:
        big_font = sub_font = ImageFont.load_default()

    # 상단 강조바
    draw.rectangle([0, 0, W, 12], fill=ACCENT)

    # 채널명
    draw.text((60, 40), "팡이의 본심 대변인", font=sub_font, fill=ACCENT)

    # 주제 텍스트 (중앙)
    max_chars = 14
    lines = [topic[i:i + max_chars] for i in range(0, len(topic), max_chars)]
    total_h = len(lines) * 100
    y = (H - total_h) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=big_font)
        x = (W - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=big_font, fill=YELLOW)
        y += 100

    # 하단 강조바
    draw.rectangle([0, H - 12, W, H], fill=ACCENT)

    try:
        img.save(output_path)
        return True
    except Exception as e:
        print(f"썸네일 생성 실패: {e}")
        return False


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
