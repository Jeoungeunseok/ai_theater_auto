import os
from sqlalchemy.orm import Session
from api.database import SessionLocal
from api.models import Job, JobStatus
from api.youtube import upload_to_youtube


def upload_video_task(job_id: str):
    """승인된 영상을 YouTube에 업로드하는 워커 태스크."""
    db: Session = SessionLocal()
    db_job = None
    try:
        db_job = db.query(Job).filter(Job.id == job_id).first()
        if not db_job:
            print(f"[{job_id}] Job not found for upload")
            return

        if not db_job.video_path or not os.path.exists(db_job.video_path):
            raise RuntimeError(f"업로드할 영상 파일이 없습니다: {db_job.video_path}")

        print(f"[{job_id}] Starting YouTube upload...")
        video_title = f"{db_job.topic} #Shorts"
        video_desc = f"AI Theater - {db_job.topic}\n#AI #Shorts #Story"

        youtube_id = upload_to_youtube(db_job.video_path, video_title, video_desc)

        if youtube_id:
            db_job.youtube_id = youtube_id
            db_job.status = JobStatus.COMPLETED
            db_job.current_step = "uploaded"
            print(f"[{job_id}] Upload successful: {youtube_id}")
        else:
            raise RuntimeError("YouTube 업로드 실패 (client 오류)")

        db.commit()

    except Exception as e:
        print(f"[{job_id}] Upload Task Failed: {e}")
        if db_job:
            db_job.status = JobStatus.FAILED
            db_job.error_log = f"Upload Error: {e}"
            db.commit()
        raise
    finally:
        db.close()
