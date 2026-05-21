import os
import hmac
import hashlib
import time
from fastapi import Request, HTTPException
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

client = WebClient(token=SLACK_BOT_TOKEN)

async def verify_slack_signature(request: Request):
    """
    Slack에서 보낸 요청인지 HMAC 서명을 통해 검증합니다.
    """
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")
    
    if not timestamp or not signature:
        raise HTTPException(status_code=400, detail="Missing Slack headers")
        
    if abs(time.time() - int(timestamp)) > 60 * 5:
        raise HTTPException(status_code=400, detail="Request too old")
        
    body = await request.body()
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    
    my_signature = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode("utf-8"),
        sig_basestring.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(my_signature, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

def send_approval_message(job_id: str, topic: str, video_path: str):
    """
    Slack으로 승인 요청 메시지를 보냅니다.
    """
    try:
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🎬 *새로운 영상 렌더링 완료!*\n*주제:* {topic}\n*ID:* `{job_id}`"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ 승인 (업로드)"},
                        "style": "primary",
                        "value": job_id,
                        "action_id": "approve_video"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ 반려"},
                        "style": "danger",
                        "value": job_id,
                        "action_id": "reject_video"
                    }
                ]
            }
        ]
        
        # 파일 업로드 (프리뷰)
        client.files_upload_v2(
            channel="#ai-theater-alerts",
            file=video_path,
            title=f"Preview_{job_id}.mp4",
            initial_comment=f"영상 '{topic}'의 렌더링이 끝났습니다. 승인하시겠습니까?"
        )
        
        # 버튼 전송
        client.chat_postMessage(channel="#ai-theater-alerts", blocks=blocks)
    except SlackApiError as e:
        print(f"Error sending to Slack: {e}")
