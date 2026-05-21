from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import uuid
import os
from redis import Redis
from rq import Queue

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
async def create_job(job: JobCreate):
    job_id = str(uuid.uuid4())
    q.enqueue("worker.tasks.create_video_task", job_id, job.topic, job_id=job_id)
    return {"job_id": job_id, "status": "PENDING"}


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    rq_job = q.fetch_job(job_id)
    if rq_job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job_id,
        "status": rq_job.get_status().value,
        "result": rq_job.result if rq_job.is_finished else None,
    }
