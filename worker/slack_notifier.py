import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

_SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "#pangi-alerts")


def _client() -> WebClient | None:
    token = os.getenv("SLACK_BOT_TOKEN")
    return WebClient(token=token) if token else None


def send_approval_message(job_id: str, topic: str, video_path: str):
    """렌더링 완료 → Slack 승인 요청 (승인 / 반려 / 재생성 버튼)."""
    client = _client()
    if not client:
        print("[WARN] SLACK_BOT_TOKEN 미설정 — Slack 알림 건너뜀")
        return

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*팡이 영상 렌더링 완료*\n주제: {topic}\nID: `{job_id}`",
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "승인 (업로드)"},
                    "style": "primary",
                    "value": job_id,
                    "action_id": "approve_video",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "반려"},
                    "style": "danger",
                    "value": job_id,
                    "action_id": "reject_video",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "재생성"},
                    "value": job_id,
                    "action_id": "regenerate_video",
                },
            ],
        },
    ]

    try:
        client.files_upload_v2(
            channel=_SLACK_CHANNEL,
            file=video_path,
            title=f"팡이 미리보기_{job_id[:8]}.mp4",
        )
        client.chat_postMessage(channel=_SLACK_CHANNEL, blocks=blocks)
    except SlackApiError as e:
        print(f"[WARN] Slack 메시지 전송 실패: {e}")


def send_error_alert(job_id: str, topic: str, error: str, retry_count: int):
    """3회 실패 시 Slack 에러 알람."""
    client = _client()
    if not client:
        print(f"[ERROR] Job {job_id} 최종 실패 (Slack 미설정): {error}")
        return

    try:
        client.chat_postMessage(
            channel=_SLACK_CHANNEL,
            text=(
                f":rotating_light: *팡이 작업 최종 실패*\n"
                f"주제: {topic}\nID: `{job_id}`\n"
                f"재시도: {retry_count}회\n"
                f"오류: `{error[:200]}`"
            ),
        )
    except SlackApiError as e:
        print(f"[WARN] 에러 알람 전송 실패: {e}")


def send_vote_report(episode_no: int, votes: dict, next_topic: str = ""):
    """투표 결과 일일 리포트."""
    client = _client()
    if not client:
        return

    lines = "\n".join(f"- {k}: {v}표" for k, v in votes.items())
    text = f"*Ep.{episode_no:02d} 다음 본심 투표 결과*\n{lines}"
    if next_topic:
        text += f"\n\n차주 확정 주제: *{next_topic}*"

    try:
        client.chat_postMessage(channel=_SLACK_CHANNEL, text=text)
    except SlackApiError as e:
        print(f"[WARN] 투표 리포트 전송 실패: {e}")
