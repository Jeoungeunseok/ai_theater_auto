import json
from db.database import SessionLocal
from db.models import Job, JobStatus, Episode
from api.youtube import upload_to_youtube

def upload_video_task(job_id: str, series_name: str = "Default", choices: list = None):
    """
    승인된 영상을 YouTube에 업로드하는 워커 태스크입니다.
    """
    db = SessionLocal()
    db_job = None
    try:
        db_job = db.query(Job).filter(Job.id == job_id).first()
        if not db_job:
            print(f"[{job_id}] Job not found for upload")
            return

        print(f"[{job_id}] Starting YouTube upload...")

        video_title = f"{db_job.topic} #Shorts"
        video_desc = f"AI Theater - {db_job.topic}\n#AI #Shorts #Story"

        youtube_id = upload_to_youtube(
            db_job.video_path,
            video_title,
            video_desc
        )

        if youtube_id:
            db_job.youtube_id = youtube_id
            db_job.status = JobStatus.COMPLETED
            db_job.current_step = "uploaded"

            last_episode = (
                db.query(Episode)
                .filter(Episode.series_name == series_name)
                .order_by(Episode.episode_no.desc())
                .first()
            )
            episode_no = (last_episode.episode_no + 1) if last_episode else 1

            new_episode = Episode(
                series_name=series_name,
                episode_no=episode_no,
                job_id=db_job.id,
                title=video_title,
                video_path=db_job.video_path,
                youtube_url=f"https://youtu.be/{youtube_id}",
                youtube_video_id=youtube_id,
                choices=json.dumps(choices, ensure_ascii=False) if choices else None,
            )
            db.add(new_episode)
            print(f"[{job_id}] Upload successful & Episode {episode_no} created: {youtube_id}")
        else:
            db_job.status = JobStatus.FAILED
            db_job.error_log = "YouTube upload failed"

        db.commit()

    except Exception as e:
        print(f"[{job_id}] Upload Task Failed: {str(e)}")
        if db_job:
            db_job.status = JobStatus.FAILED
            db_job.error_log = f"Upload Error: {str(e)}"
            db.commit()
    finally:
        db.close()
