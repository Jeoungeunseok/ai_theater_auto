import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "#ai-theater-alerts")

_client = WebClient(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None


def send_approval_message(job_id: str, topic: str, video_path: str):
    """렌더링 완료 후 Slack으로 승인 요청 전송."""
    if not _client:
        print("[WARN] SLACK_BOT_TOKEN 미설정 — Slack 알림 건너뜀")
        return

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🎬 *새로운 영상 렌더링 완료!*\n*주제:* {topic}\n*ID:* `{job_id}`",
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ 승인 (업로드)"},
                    "style": "primary",
                    "value": job_id,
                    "action_id": "approve_video",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ 반려"},
                    "style": "danger",
                    "value": job_id,
                    "action_id": "reject_video",
                },
            ],
        },
    ]

    _client.files_upload_v2(
        channel=SLACK_CHANNEL,
        file=video_path,
        title=f"Preview_{job_id}.mp4",
        initial_comment=f"영상 '{topic}'의 렌더링이 끝났습니다. 승인하시겠습니까?",
    )
    _client.chat_postMessage(channel=SLACK_CHANNEL, blocks=blocks)
