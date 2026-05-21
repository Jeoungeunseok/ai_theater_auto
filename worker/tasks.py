import os
import asyncio
import json
from db.database import SessionLocal
from db.models import Job, JobStatus
from scripts.generate_script import generate_short_script
from scripts.generate_voice import generate_voice_over
from scripts.fetch_assets import fetch_pexels_image
from scripts.render_short import render_full_short
from api.slack import send_approval_message

def create_video_task(job_id: str, topic: str, series_name: str = "folktale"):
    """
    RQ 워커가 실행할 실제 영상 제작 태스크입니다.
    """
    db = SessionLocal()
    db_job = None
    try:
        db_job = db.query(Job).filter(Job.id == job_id).first()
        if not db_job:
            print(f"[{job_id}] Job not found")
            return

        db_job.status = JobStatus.PROCESSING
        db_job.series_name = series_name
        db.commit()

        tmp_dir = f"tmp/aitheater/{job_id}"
        os.makedirs(tmp_dir, exist_ok=True)

        # 1. 대본 생성
        print(f"[{job_id}] Step 1: Generating Script for {series_name}")
        db_job.current_step = "generating_script"
        db.commit()
        script = generate_short_script(topic, series_name=series_name)
        script_path = os.path.join(tmp_dir, "script.json")
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)

        # 2. 음성 생성
        print(f"[{job_id}] Step 2: Generating Voice")
        db_job.current_step = "generating_voice"
        db.commit()
        voice_dir = os.path.join(tmp_dir, "voice")
        asyncio.run(generate_voice_over(script_path, voice_dir))

        # 3. 배경 이미지 수집
        print(f"[{job_id}] Step 3: Fetching Background")
        db_job.current_step = "fetching_assets"
        db.commit()
        bg_path = os.path.join(tmp_dir, "background.jpg")
        fetch_pexels_image("cinematic landscape", bg_path)

        # 4. 영상 렌더링
        print(f"[{job_id}] Step 4: Rendering Video")
        db_job.current_step = "rendering"
        db.commit()
        output_video = os.path.join(tmp_dir, "final.mp4")
        render_full_short(script_path, voice_dir, bg_path, output_video)

        # choices 추출 후 job에 저장
        choices = script.get("choices")
        db_job.video_path = output_video
        db_job.choices = json.dumps(choices, ensure_ascii=False) if choices else None
        db_job.current_step = "pending_approval"
        db.commit()

        # 5. Slack 승인 요청
        send_approval_message(job_id, topic, output_video)
        print(f"[{job_id}] Task Completed Successfully: {output_video}")

    except Exception as e:
        print(f"[{job_id}] Task Failed: {str(e)}")
        if db_job:
            db_job.status = JobStatus.FAILED
            db_job.error_log = f"Task Error: {str(e)}"
            db.commit()
        raise e
    finally:
        db.close()
