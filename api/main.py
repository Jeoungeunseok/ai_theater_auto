from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import uuid
import os
from redis import Redis
from rq import Queue
from sqlalchemy.orm import Session
from .database import get_db
from .models import Job, JobStatus

app = FastAPI(title="AI Theater API")

# Redis 및 RQ 설정
redis_conn = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
q = Queue(connection=redis_conn)

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
    # 1. DB에 작업 저장
    new_job = Job(
        id=uuid.uuid4(),
        topic=job_data.topic,
        status=JobStatus.PENDING
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    
    job_id = str(new_job.id)
    
    # 2. RQ 큐에 작업 추가
    q.enqueue('worker.tasks.create_video_task', job_id, job_data.topic, job_id=job_id)
    
    return {"job_id": job_id, "status": "PENDING"}

@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str, db: Session = Depends(get_db)):
    # DB에서 작업 조회
    db_job = db.query(Job).filter(Job.id == job_id).first()
    if db_job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "job_id": str(db_job.id),
        "status": db_job.status,
        "current_step": db_job.current_step,
        "video_path": db_job.video_path,
        "error_log": db_job.error_log
    }
