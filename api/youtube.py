import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def get_youtube_client():
    """
    저장된 credentials를 사용하여 YouTube API 클라이언트를 빌드합니다.
    (실제 구현 시에는 Refresh Token을 DB에서 관리해야 함)
    """
    # 임시: 환경 변수에서 client secret 등을 가져와 인증
    # 실제로는 Phase 4 로드맵에 따라 OAuth 2.0 flow 구현 필요
    credentials_dict = {
        "token": os.getenv("YOUTUBE_ACCESS_TOKEN"),
        "refresh_token": os.getenv("YOUTUBE_REFRESH_TOKEN"),
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": os.getenv("YOUTUBE_CLIENT_ID"),
        "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET"),
        "scopes": SCOPES
    }
    
    if not credentials_dict["token"]:
        print("YouTube credentials missing in .env")
        return None
        
    credentials = Credentials(**credentials_dict)
    return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)

def upload_to_youtube(video_path, title, description, tags=None):
    """
    영상을 YouTube에 업로드합니다 (Resumable Upload).
    """
    youtube = get_youtube_client()
    if not youtube:
        return None

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or ["Shorts", "AI"],
            "categoryId": "24" # Entertainment
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(
        video_path, 
        mimetype="video/mp4", 
        resumable=True
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploaded {int(status.progress() * 100)}%")

    print(f"Upload Complete! Video ID: {response['id']}")
    return response['id']
