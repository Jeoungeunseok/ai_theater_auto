import json
import os
from db.database import SessionLocal
from db.models import Job, JobStatus, Episode
from api.youtube import upload_to_youtube, generate_thumbnail, build_tags
from scripts.daily_cost import record_cost
from worker.slack_notifier import send_thumbnail_approval


def generate_thumbnail_task(job_id: str):
    """썸네일 생성 → Slack 확인 게이트 (영상 승인 직후 실행)."""
    db = SessionLocal()
    job = None
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            print(f"[{job_id}] Job not found for thumbnail generation")
            return

        tmp_dir = os.path.dirname(job.video_path) if job.video_path else f"tmp/aitheater/{job_id}"
        hooking_line = _load_hooking_line(job.video_path)
        thumbnail_path = os.path.join(tmp_dir, "thumbnail.jpg")

        job.current_step = "generating_thumbnail"
        db.commit()

        generate_thumbnail(job.topic, thumbnail_path, category=job.category, hook_line=hooking_line)
        record_cost("thumbnail")

        job.current_step = "pending_thumbnail_approval"
        db.commit()

        send_thumbnail_approval(job_id, job.topic, thumbnail_path)
        print(f"[{job_id}] 썸네일 생성 완료 — Slack 확인 대기")

    except Exception as e:
        print(f"[{job_id}] generate_thumbnail_task 실패: {e}")
        if job:
            job.error_log = f"Thumbnail Error: {e}"
            db.commit()
    finally:
        db.close()


def upload_video_task(job_id: str):
    """썸네일 확정 후 YouTube 업로드 (썸네일은 이미 생성된 상태)."""
    db = SessionLocal()
    job = None
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            print(f"[{job_id}] Job not found for upload")
            return

        topic = job.topic
        category = job.category
        episode_no = job.episode_no or 1
        vote_options = json.loads(job.vote_options) if job.vote_options else []
        tmp_dir = os.path.dirname(job.video_path) if job.video_path else f"tmp/aitheater/{job_id}"

        hooking_line = _load_hooking_line(job.video_path)
        title = (
            f"{hooking_line} | 팡이 Ep.{episode_no:02d}"
            if hooking_line else
            f"{topic} | 팡이 Ep.{episode_no:02d}"
        )

        vote_text = " / ".join(vote_options)
        desc = (
            f"팡이가 까발려드리는 본심 이야기\n\n"
            f"다음 주제 투표: {vote_text}\n\n"
            f"#팡이 #본심대변인 #Shorts #{category}\n\n"
            f"ref:{job_id}"
        )

        thumbnail_path = os.path.join(tmp_dir, "thumbnail.jpg")

        print(f"[{job_id}] YouTube 업로드 시작: {title}")
        youtube_id = upload_to_youtube(
            video_path=job.video_path,
            title=title,
            description=desc,
            category=category,
            tags=build_tags(category),
            thumbnail_path=thumbnail_path,
        )

        if youtube_id:
            job.youtube_id = youtube_id
            job.status = JobStatus.COMPLETED
            job.current_step = "uploaded"

            new_episode = Episode(
                category=category,
                episode_no=episode_no,
                job_id=job.id,
                title=title,
                video_path=job.video_path,
                youtube_url=f"https://youtu.be/{youtube_id}",
                youtube_video_id=youtube_id,
                vote_options=json.dumps(vote_options, ensure_ascii=False),
            )
            db.add(new_episode)
            print(f"[{job_id}] 업로드 완료 & Ep.{episode_no:02d} 생성: {youtube_id}")
        else:
            job.status = JobStatus.FAILED
            job.error_log = "YouTube 업로드 실패"

        db.commit()

    except Exception as e:
        print(f"[{job_id}] Upload 실패: {e}")
        if job:
            job.status = JobStatus.FAILED
            job.error_log = f"Upload Error: {e}"
            db.commit()
    finally:
        db.close()


def _load_hooking_line(video_path: str) -> str:
    """script.json에서 후킹 beat 대사 로드."""
    if not video_path:
        return ""
    script_path = os.path.join(os.path.dirname(video_path), "script.json")
    if not os.path.exists(script_path):
        return ""
    try:
        with open(script_path, encoding="utf-8") as f:
            data = json.load(f)
        hooking = next((b for b in data.get("beats", []) if b.get("beat") == "후킹"), None)
        return hooking.get("dialogue", "")[:30] if hooking else ""
    except Exception:
        return ""
