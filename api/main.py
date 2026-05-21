from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
import uuid
import os
import json
from redis import Redis
from rq import Queue
from sqlalchemy.orm import Session
from database import get_db
from models import Job, JobStatus
from slack import verify_slack_signature

app = FastAPI(title="AI Theater API")

redis_conn = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
q = Queue("render_queue", connection=redis_conn)


class JobCreate(BaseModel):
    topic: str
    series_name: Optional[str] = "Default"


class JobResponse(BaseModel):
    job_id: str
    status: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def read_root():
    return {"message": "AI Theater API is running"}


@app.post("/jobs", response_model=JobResponse)
async def create_job(job_data: JobCreate, db: Session = Depends(get_db)):
    job_id = uuid.uuid4()
    new_job = Job(id=job_id, topic=job_data.topic, status=JobStatus.PENDING)
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    try:
        q.enqueue("worker.tasks.create_video_task", str(job_id), job_data.topic, job_id=str(job_id))
    except Exception as e:
        db.delete(new_job)
        db.commit()
        raise HTTPException(status_code=503, detail=f"큐 추가 실패: {e}")

    return {"job_id": str(job_id), "status": "PENDING"}


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str, db: Session = Depends(get_db)):
    db_job = db.query(Job).filter(Job.id == job_id).first()
    if db_job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": str(db_job.id),
        "status": db_job.status.value,
        "current_step": db_job.current_step,
        "video_path": db_job.video_path,
        "error_log": db_job.error_log,
    }


@app.post("/slack/actions")
async def slack_actions(request: Request, db: Session = Depends(get_db)):
    await verify_slack_signature(request)

    form_data = await request.form()
    payload = json.loads(form_data["payload"])

    action = payload["actions"][0]
    job_id = action["value"]
    action_id = action["action_id"]

    db_job = db.query(Job).filter(Job.id == job_id).first()
    if not db_job:
        return {"ok": False, "error": "Job not found"}

    if action_id == "approve_video":
        db_job.current_step = "approved"
        # Phase 4: YouTube 업로드 큐로 전달
        q.enqueue('worker.upload_tasks.upload_video_task', job_id)
    elif action_id == "reject_video":
        db_job.status = JobStatus.FAILED
        db_job.error_log = "User rejected the video via Slack."

    db.commit()
    return {"ok": True}
