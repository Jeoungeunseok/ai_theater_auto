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


def send_script_approval(job_id: str, topic: str, script: dict):
    """v4 §3.3 — 대본 게이트(가장 싼 단계). 비싼 I2V 전에 대본부터 슬랙 승인."""
    client = _client()
    if not client:
        print("[WARN] SLACK_BOT_TOKEN 미설정 — 대본 게이트 자동 통과")
        return

    beat_lines = "\n".join(
        f"*[{b.get('beat','')}]* ({b.get('emotion','')}) {b.get('dialogue','')}"
        for b in script.get("beats", [])
    )
    text = f"*📜 대본 확인 — {topic}*\nID: `{job_id}`\n\n{beat_lines}"

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "대본 승인 (제작 시작)"},
                    "style": "primary",
                    "value": job_id,
                    "action_id": "approve_script",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "대본 재생성"},
                    "value": job_id,
                    "action_id": "regenerate_script",
                },
            ],
        },
    ]
    try:
        client.chat_postMessage(channel=_SLACK_CHANNEL, blocks=blocks, text=f"대본 확인: {topic}")
    except SlackApiError as e:
        print(f"[WARN] 대본 게이트 메시지 전송 실패: {e}")


def send_regen_limit_warning(job_id: str, topic: str, limit: int):
    """v4 §3.5 — 에피소드당 재생성 상한 도달 경고."""
    client = _client()
    if not client:
        print(f"[COST] Job {job_id} 재생성 상한({limit}) 도달 — 재생성 차단")
        return
    try:
        client.chat_postMessage(
            channel=_SLACK_CHANNEL,
            text=(
                f":warning: *이번 편 리롤 한도 도달*\n"
                f"주제: {topic}\nID: `{job_id}`\n"
                f"재생성 {limit}회 초과 — 추가 재생성이 차단되었습니다. "
                f"승인하거나 반려해주세요."
            ),
        )
    except SlackApiError as e:
        print(f"[WARN] 리롤 한도 경고 전송 실패: {e}")


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


def send_image_candidates(job_id: str, beat_idx: int, beat_name: str, emotion: str,
                          candidate_paths: list[str], n_beats: int):
    """컷별 이미지 후보 Slack 전송. 사용자가 하나 선택하면 I2V로 넘어간다.

    후보 이미지 파일을 채널에 업로드한 뒤, 번호별 선택 버튼 메시지를 전송한다.
    SLACK_BOT_TOKEN 미설정 시 자동 통과(body_front.png 폴백은 produce_video_task가 처리).
    """
    client = _client()
    if not client:
        print(f"[WARN] SLACK_BOT_TOKEN 미설정 — beat_{beat_idx} 이미지 게이트 자동 통과")
        return

    # 후보 이미지 채널 업로드
    for i, path in enumerate(candidate_paths):
        try:
            client.files_upload_v2(
                channel=_SLACK_CHANNEL,
                file=path,
                title=f"beat_{beat_idx:02d}_candidate_{i+1} ({beat_name}/{emotion})",
            )
        except SlackApiError as e:
            print(f"[WARN] 이미지 업로드 실패 (candidate {i}): {e}")

    # 선택 버튼 — action_id는 beat·후보 index 인코딩, value에 경로 담기
    buttons = [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": f"이미지 {i+1}"},
            "value": f"{job_id}|{beat_idx}|{path}",
            "action_id": f"select_image_b{beat_idx}_c{i}",
        }
        for i, path in enumerate(candidate_paths)
    ] + [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "다시 생성"},
            "value": f"{job_id}|{beat_idx}",
            "action_id": f"regenerate_image_b{beat_idx}",
        }
    ]

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*컷 {beat_idx+1}/{n_beats} 이미지 선택* "
                    f"— `{beat_name}` / {emotion}\n"
                    f"ID: `{job_id}`\n어떤 이미지로 I2V를 진행할까요?"
                ),
            },
        },
        {"type": "actions", "elements": buttons},
    ]

    try:
        client.chat_postMessage(
            channel=_SLACK_CHANNEL,
            blocks=blocks,
            text=f"컷 {beat_idx+1}/{n_beats} 이미지 선택 — {beat_name}/{emotion}",
        )
    except SlackApiError as e:
        print(f"[WARN] 이미지 후보 메시지 전송 실패: {e}")


def update_image_regenerating(channel_id: str, message_ts: str, beat_idx: int, n_beats: int):
    """'다시 생성' 클릭 직후 해당 메시지를 '재생성 중...' 상태로 교체."""
    client = _client()
    if not client:
        return
    try:
        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f":arrows_counterclockwise: *컷 {beat_idx + 1}/{n_beats} 이미지 재생성 중...*",
                    },
                }
            ],
            text=f"컷 {beat_idx + 1}/{n_beats} 재생성 중...",
        )
    except SlackApiError as e:
        print(f"[WARN] 재생성 중 메시지 업데이트 실패: {e}")


def update_image_selected(
    channel_id: str,
    message_ts: str,
    beat_idx: int,
    beat_name: str,
    emotion: str,
    candidate_no: int,
    n_beats: int,
):
    """이미지 선택 버튼 클릭 후 해당 Slack 메시지를 '선택 완료' 상태로 교체."""
    client = _client()
    if not client:
        return
    try:
        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f":white_check_mark: *컷 {beat_idx + 1}/{n_beats} 선택 완료*"
                            f" — `{beat_name}` / {emotion}\n"
                            f"이미지 {candidate_no} 선택됨"
                        ),
                    },
                }
            ],
            text=f"컷 {beat_idx + 1}/{n_beats} 이미지 {candidate_no} 선택됨",
        )
    except SlackApiError as e:
        print(f"[WARN] 이미지 선택 메시지 업데이트 실패: {e}")


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
