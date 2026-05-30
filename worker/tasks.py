import os
import json
import shutil
import datetime
from db.database import SessionLocal
from db.models import Job, JobStatus, Episode
from scripts.generate_script import generate_pangi_script
from scripts.generate_clips import generate_all_clips
from scripts.generate_voice import generate_pangi_voice
from scripts.generate_image import generate_background
from scripts.render_short import render_pangi_short
from scripts.daily_cost import is_queue_paused, record_cost
from worker.slack_notifier import send_approval_message, send_script_approval, send_error_alert

_RETRY_DELAYS = [60, 300, 1800]  # 1분 → 5분 → 30분


def _next_episode_no(db, category: str) -> int:
    last = (
        db.query(Episode)
        .filter(Episode.category == category)
        .order_by(Episode.episode_no.desc())
        .first()
    )
    return (last.episode_no + 1) if last else 1


def _tmp_dir(job_id: str) -> str:
    d = f"tmp/aitheater/{job_id}"
    os.makedirs(d, exist_ok=True)
    return d


# ── 1단계: 대본 생성 + 대본 게이트 (v4 §3.3, 가장 싼 단계) ──

def create_script_task(job_id: str, topic: str, category: str = "직장", episode_no: int = None):
    db = SessionLocal()
    job = None
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            print(f"[{job_id}] Job not found")
            return
        if is_queue_paused():
            print(f"[{job_id}] 일일 비용 한도 초과 — 큐 정지 중")
            return

        if episode_no is None:
            episode_no = _next_episode_no(db, category)

        job.status = JobStatus.PROCESSING
        job.category = category
        job.episode_no = episode_no
        _step(db, job, "generating_script")

        script = generate_pangi_script(topic, category=category, episode_no=episode_no)
        record_cost("script")

        tmp_dir = _tmp_dir(job_id)
        script_path = os.path.join(tmp_dir, "script.json")
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)

        # 대본이 새로 나오면 이전 I2V 클립은 무효 — 스테일 재사용 방지
        clips_dir = os.path.join(tmp_dir, "clips")
        if os.path.isdir(clips_dir):
            shutil.rmtree(clips_dir)

        job.vote_options = json.dumps(script.get("vote_options", []), ensure_ascii=False)
        job.current_step = "pending_script_approval"
        db.commit()

        # 대본 게이트 — 승인 시에만 비싼 제작 단계로
        send_script_approval(job_id, topic, script)
        print(f"[{job_id}] 대본 생성 완료 — 슬랙 대본 승인 대기")

    except Exception as e:
        _handle_failure(db, job, job_id, topic, category, episode_no, e,
                        "worker.tasks.create_script_task")
        raise
    finally:
        db.close()


# ── 2단계: 영상 제작 + 최종 게이트 (대본 승인 후) ──────────

def produce_video_task(job_id: str, topic: str, category: str = "직장", episode_no: int = None):
    db = SessionLocal()
    job = None
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            print(f"[{job_id}] Job not found")
            return
        if is_queue_paused():
            print(f"[{job_id}] 일일 비용 한도 초과 — 큐 정지 중")
            return

        episode_no = episode_no or job.episode_no or _next_episode_no(db, category)
        job.status = JobStatus.PROCESSING
        tmp_dir = _tmp_dir(job_id)

        # 승인된 대본 로드 (없으면 방어적으로 재생성)
        script_path = os.path.join(tmp_dir, "script.json")
        if os.path.exists(script_path):
            with open(script_path, encoding="utf-8") as f:
                script = json.load(f)
        else:
            _step(db, job, "generating_script")
            script = generate_pangi_script(topic, category=category, episode_no=episode_no)
            record_cost("script")
            with open(script_path, "w", encoding="utf-8") as f:
                json.dump(script, f, ensure_ascii=False, indent=2)

        # 1. 배경 이미지
        _step(db, job, "generating_background")
        bg_path = f"assets/bg/ep{episode_no:02d}_{category}.webp"
        if not os.path.exists(bg_path):
            generate_background(topic, category=category, output_path=bg_path)
            record_cost("background")

        # 2. Kling I2V 클립 (⭐ 최대 비용 — 새로 생성된 클립만 과금)
        _step(db, job, "generating_clips")
        clips_dir = os.path.join(tmp_dir, "clips")
        if os.getenv("FAL_KEY"):
            before = set(os.listdir(clips_dir)) if os.path.isdir(clips_dir) else set()
            clip_paths = generate_all_clips(script, clips_dir)
            for p in clip_paths:
                if os.path.basename(p) not in before:
                    record_cost("i2v")
        else:
            print(f"[{job_id}] FAL_KEY 미설정 — I2V 건너뛰고 폴백 렌더")

        # 3. 보이스
        _step(db, job, "generating_voice")
        voice_dir = os.path.join(tmp_dir, "voice")
        generate_pangi_voice(script_path, output_dir=voice_dir)

        # 4. 렌더링 (clips 있으면 Kling, 없으면 폴백 자동 선택)
        _step(db, job, "rendering")
        output_path = os.path.join(tmp_dir, "final.mp4")
        render_pangi_short(
            script_path=script_path,
            voice_dir=voice_dir,
            bg_path=bg_path,
            output_path=output_path,
            category=category,
        )

        job.status = JobStatus.COMPLETED
        job.video_path = output_path
        job.vote_options = json.dumps(script.get("vote_options", []), ensure_ascii=False)
        job.current_step = "pending_approval"
        db.commit()

        # 최종 영상 게이트
        send_approval_message(job_id, topic, output_path)
        print(f"[{job_id}] 제작 완료: {output_path}")

    except Exception as e:
        _handle_failure(db, job, job_id, topic, category, episode_no, e,
                        "worker.tasks.produce_video_task")
        raise
    finally:
        db.close()


# ── 공통 헬퍼 ─────────────────────────────────────────────

def _step(db, job, step: str):
    job.current_step = step
    job.updated_at = datetime.datetime.utcnow()
    db.commit()


def _handle_failure(db, job, job_id, topic, category, episode_no, e, retry_task: str):
    print(f"[{job_id}] 실패: {e}")
    if not job:
        return
    job.retry_count = (job.retry_count or 0) + 1
    job.error_log = str(e)

    if job.retry_count <= len(_RETRY_DELAYS):
        delay = _RETRY_DELAYS[job.retry_count - 1]
        job.status = JobStatus.PENDING
        job.current_step = f"retry_{job.retry_count}"
        db.commit()
        _enqueue_retry(retry_task, job_id, topic, category, episode_no, delay)
        print(f"[{job_id}] {delay}초 후 재시도 ({job.retry_count}회차)")
    else:
        job.status = JobStatus.FAILED
        db.commit()
        send_error_alert(job_id, topic, str(e), job.retry_count)
        print(f"[{job_id}] 3회 실패 — Slack 에러 알람 발송")


def _enqueue_retry(task: str, job_id: str, topic: str, category: str,
                   episode_no: int, delay_sec: int):
    from redis import Redis
    from rq import Queue
    import datetime as dt
    redis_conn = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
    q = Queue("render_queue", connection=redis_conn)
    q.enqueue_in(
        dt.timedelta(seconds=delay_sec),
        task,
        job_id, topic, category, episode_no,
    )
