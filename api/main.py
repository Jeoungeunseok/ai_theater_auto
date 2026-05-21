from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import uuid

app = FastAPI(title="AI Theater API")

class JobCreate(BaseModel):
    topic: str
    series_name: Optional[str] = "Default"

class JobResponse(BaseModel):
    job_id: str
    status: str

@app.get("/")
def read_root():
    return {"message": "AI Theater API is running"}

@app.post("/jobs", response_model=JobResponse)
async def create_job(job: JobCreate):
    # TODO: DB에 작업 저장 및 Redis Queue에 작업 추가
    job_id = str(uuid.uuid4())
    return {"job_id": job_id, "status": "PENDING"}

@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    # TODO: DB에서 작업 상태 조회
    return {"job_id": job_id, "status": "PROCESSING", "current_step": "generating_script"}
