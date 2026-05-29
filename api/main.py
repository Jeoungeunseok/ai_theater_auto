import os
import json
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
from redis import Redis
from rq import Queue
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Job, JobStatus
from api.slack import verify_slack_signature

app = FastAPI(title="팡이 API")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_conn = Redis.from_url(REDIS_URL)
render_queue = Queue("render_queue", connection=redis_conn)
upload_queue = Queue("upload_queue", connection=redis_conn)


class JobCreate(BaseModel):
    topic: str
    category: str = "직장"             # 직장 | 욕망 | 부부 | 일상
    episode_no: Optional[int] = None   # None이면 DB에서 자동 계산


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
    action = payload["actions"][0]
    job_id = action["value"]
    action_id = action["action_id"]

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
        job.status = JobStatus.FAILED
        job.error_log = "Slack에서 반려됨"

    db.commit()
    return {"ok": True}
