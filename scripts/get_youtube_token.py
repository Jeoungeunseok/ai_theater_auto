"""
YouTube OAuth2 Refresh Token 발급 스크립트.
최초 1회만 실행 — 이후 access token은 api/youtube.py가 자동 갱신.

사용법:
  python scripts/get_youtube_token.py
  → 브라우저 열림 → Google 계정 로그인 → 허용
  → 터미널에 YOUTUBE_REFRESH_TOKEN 출력 → .env에 복붙
"""
import os
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

client_id     = os.getenv("YOUTUBE_CLIENT_ID")
client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

if not client_id or not client_secret:
    raise SystemExit("❌ .env에 YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET 없음")

client_config = {
    "installed": {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uris": ["http://localhost", "urn:ietf:wg:oauth:2.0:oob"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
creds = flow.run_local_server(port=0)

print("\n" + "=" * 60)
print("✅ 발급 완료! 아래 값을 .env에 복붙하세요:\n")
print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")
print("=" * 60)
