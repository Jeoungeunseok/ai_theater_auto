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

app = FastAPI(title="AI Theater API")

# Redis 및 RQ 설정 (환경변수 관리)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
RENDER_QUEUE_NAME = os.getenv("RENDER_QUEUE", "render_queue")
UPLOAD_QUEUE_NAME = os.getenv("UPLOAD_QUEUE", "upload_queue")

redis_conn = Redis.from_url(REDIS_URL)
render_queue = Queue(RENDER_QUEUE_NAME, connection=redis_conn)
upload_queue = Queue(UPLOAD_QUEUE_NAME, connection=redis_conn)

class JobCreate(BaseModel):
    topic: str
    series_name: Optional[str] = "Default"

class JobResponse(BaseModel):
    job_id: str
    status: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/jobs", response_model=JobResponse)
async def create_job(job_data: JobCreate, db: Session = Depends(get_db)):
    job_id = uuid.uuid4()
    new_job = Job(
        id=job_id,
        topic=job_data.topic,
        status=JobStatus.PENDING
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    
    render_queue.enqueue('worker.tasks.create_video_task', str(job_id), job_data.topic, job_data.series_name)
    
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
        "youtube_id": db_job.youtube_id,
        "error_log": db_job.error_log
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
        choices = json.loads(db_job.choices) if db_job.choices else None
        upload_queue.enqueue(
            'worker.upload_tasks.upload_video_task',
            job_id,
            db_job.series_name or "Default",
            choices,
        )
    elif action_id == "reject_video":
        db_job.status = JobStatus.FAILED
        db_job.error_log = "User rejected the video via Slack."
        
    db.commit()
    return {"ok": True}
