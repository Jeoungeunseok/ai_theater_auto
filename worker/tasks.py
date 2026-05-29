import os
import json
import datetime
from db.database import SessionLocal
from db.models import Job, JobStatus, Episode
from scripts.generate_script import generate_pangi_script
from scripts.generate_voice import generate_pangi_voice
from scripts.generate_image import generate_background
from scripts.render_short import render_pangi_short
from worker.slack_notifier import send_approval_message, send_error_alert

_RETRY_DELAYS = [60, 300, 1800]  # 1분 → 5분 → 30분


def _next_episode_no(db, category: str) -> int:
    last = (
        db.query(Episode)
        .filter(Episode.category == category)
        .order_by(Episode.episode_no.desc())
        .first()
    )
    return (last.episode_no + 1) if last else 1


def create_video_task(job_id: str, topic: str, category: str = "직장", episode_no: int = None):
    db = SessionLocal()
    job = None
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            print(f"[{job_id}] Job not found")
            return

        if episode_no is None:
            episode_no = _next_episode_no(db, category)

        job.status = JobStatus.PROCESSING
        job.category = category
        job.episode_no = episode_no
        db.commit()

        tmp_dir = f"tmp/aitheater/{job_id}"
        os.makedirs(tmp_dir, exist_ok=True)

        # 1. 대본 생성
        _step(db, job, "generating_script")
        script = generate_pangi_script(topic, category=category, episode_no=episode_no)
        script_path = os.path.join(tmp_dir, "script.json")
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)

        # 2. 배경 이미지 생성
        _step(db, job, "generating_background")
        bg_path = f"assets/bg/ep{episode_no:02d}_{category}.webp"
        if not os.path.exists(bg_path):
            generate_background(topic, category=category, output_path=bg_path)

        # 3. 보이스 생성
        _step(db, job, "generating_voice")
        voice_dir = os.path.join(tmp_dir, "voice")
        generate_pangi_voice(script_path, output_dir=voice_dir)

        # 4. 렌더링
        _step(db, job, "rendering")
        output_path = os.path.join(tmp_dir, "final.mp4")
        render_pangi_short(
            script_path=script_path,
            voice_dir=voice_dir,
            bg_path=bg_path,
            output_path=output_path,
        )

        vote_options = script.get("vote_options", [])
        job.status = JobStatus.COMPLETED
        job.video_path = output_path
        job.vote_options = json.dumps(vote_options, ensure_ascii=False)
        job.current_step = "pending_approval"
        db.commit()

        # 5. Slack 승인 요청
        send_approval_message(job_id, topic, output_path)
        print(f"[{job_id}] 완료: {output_path}")

    except Exception as e:
        print(f"[{job_id}] 실패: {e}")
        if job:
            job.retry_count = (job.retry_count or 0) + 1
            job.error_log = str(e)

            if job.retry_count <= len(_RETRY_DELAYS):
                delay = _RETRY_DELAYS[job.retry_count - 1]
                job.status = JobStatus.PENDING
                job.current_step = f"retry_{job.retry_count}"
                db.commit()
                _enqueue_retry(job_id, topic, category, episode_no, delay)
                print(f"[{job_id}] {delay}초 후 재시도 ({job.retry_count}회차)")
            else:
                job.status = JobStatus.FAILED
                db.commit()
                send_error_alert(job_id, topic, str(e), job.retry_count)
                print(f"[{job_id}] 3회 실패 — Slack 에러 알람 발송")
        raise
    finally:
        db.close()


def _step(db, job, step: str):
    job.current_step = step
    job.updated_at = datetime.datetime.utcnow()
    db.commit()


def _enqueue_retry(job_id: str, topic: str, category: str, episode_no: int, delay_sec: int):
    from redis import Redis
    from rq import Queue
    import datetime as dt
    redis_conn = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
    q = Queue("render_queue", connection=redis_conn)
    q.enqueue_in(
        dt.timedelta(seconds=delay_sec),
        create_video_task,
        job_id, topic, category, episode_no,
    )
