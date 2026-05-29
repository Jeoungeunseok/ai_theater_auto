import os
import json
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
from redis import Redis
from rq import Queue
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Job, JobStatus
from api.slack import verify_slack_signature

app = FastAPI(title="팡이 API")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_conn = Redis.from_url(REDIS_URL)
render_queue = Queue("render_queue", connection=redis_conn)
upload_queue = Queue("upload_queue", connection=redis_conn)


def _slack_client() -> WebClient | None:
    token = os.getenv("SLACK_BOT_TOKEN")
    return WebClient(token=token) if token else None


class JobCreate(BaseModel):
    topic: str
    category: str = "직장"
    episode_no: Optional[int] = None


class JobResponse(BaseModel):
    job_id: str
    status: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/jobs", response_model=JobResponse)
async def create_job(body: JobCreate, db: Session = Depends(get_db)):
    job_id = uuid.uuid4()
    new_job = Job(
        id=job_id,
        topic=body.topic,
        category=body.category,
        episode_no=body.episode_no,
        status=JobStatus.PENDING,
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    render_queue.enqueue(
        "worker.tasks.create_video_task",
        str(job_id),
        body.topic,
        body.category,
        body.episode_no,
    )
    return {"job_id": str(job_id), "status": "PENDING"}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": str(job.id),
        "status": job.status.value,
        "current_step": job.current_step,
        "category": job.category,
        "episode_no": job.episode_no,
        "video_path": job.video_path,
        "youtube_id": job.youtube_id,
        "retry_count": job.retry_count,
        "error_log": job.error_log,
    }


@app.post("/slack/actions")
async def slack_actions(request: Request, db: Session = Depends(get_db)):
    await verify_slack_signature(request)

    form_data = await request.form()
    payload = json.loads(form_data["payload"])
    payload_type = payload.get("type")

    # ── 반려 사유 모달 제출 ─────────────────────────────────
    if payload_type == "view_submission":
        callback_id = payload["view"].get("callback_id")
        if callback_id == "reject_reason_modal":
            job_id = payload["view"]["private_metadata"]
            reason = (
                payload["view"]["state"]["values"]
                .get("reason_block", {})
                .get("reason_input", {})
                .get("value", "")
            )
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = JobStatus.FAILED
                job.error_log = f"반려 사유: {reason}"
                db.commit()
        return {}  # Slack은 view_submission에 빈 응답 기대

    # ── 버튼 액션 ──────────────────────────────────────────
    action = payload["actions"][0]
    job_id = action["value"]
    action_id = action["action_id"]
    trigger_id = payload.get("trigger_id")

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return {"ok": False, "error": "Job not found"}

    if action_id == "approve_video":
        job.current_step = "approved"
        vote_options = json.loads(job.vote_options) if job.vote_options else []
        upload_queue.enqueue(
            "worker.upload_tasks.upload_video_task",
            job_id,
            job.topic,
            job.category,
            job.episode_no,
            vote_options,
        )

    elif action_id == "reject_video":
        # 모달 열어서 사유 입력받기
        _open_reject_modal(trigger_id, job_id)
        return {"ok": True}  # 모달 오픈 후 즉시 응답

    elif action_id == "regenerate_video":
        job.status = JobStatus.PENDING
        job.current_step = "regenerating"
        job.retry_count = 0
        job.error_log = None
        render_queue.enqueue(
            "worker.tasks.create_video_task",
            str(job_id),
            job.topic,
            job.category,
            job.episode_no,
        )

    db.commit()
    return {"ok": True}


def _open_reject_modal(trigger_id: str, job_id: str):
    """반려 사유 입력 모달 오픈."""
    client = _slack_client()
    if not client or not trigger_id:
        return
    try:
        client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": "reject_reason_modal",
                "private_metadata": job_id,
                "title": {"type": "plain_text", "text": "반려 사유"},
                "submit": {"type": "plain_text", "text": "확인"},
                "close": {"type": "plain_text", "text": "취소"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "reason_block",
                        "label": {"type": "plain_text", "text": "반려 사유를 입력해주세요"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "reason_input",
                            "multiline": True,
                            "placeholder": {
                                "type": "plain_text",
                                "text": "예: 후킹이 약함, 톤이 너무 무거움...",
                            },
                        },
                    }
                ],
            },
        )
    except SlackApiError as e:
        print(f"[WARN] 반려 모달 오픈 실패: {e}")
