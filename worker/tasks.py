import os
import json
import shutil
import datetime
from db.database import SessionLocal
from db.models import Job, JobStatus, Episode
from scripts.generate_script import generate_pangi_script
from scripts.generate_clips import generate_all_clips
from scripts.generate_voice import generate_pangi_voice, measure_beat_durations
from scripts.generate_image import generate_background
from scripts.render_short import render_pangi_short
from scripts.daily_cost import is_queue_paused, record_cost
from scripts.generate_image import generate_cut_images
from worker.slack_notifier import (
    send_approval_message, send_script_approval, send_error_alert,
    send_image_candidates,
)

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

def create_script_task(job_id: str, topic: str, category: str = "직장", episode_no: int = None,
                       extra_instruction: str = ""):
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

        script = generate_pangi_script(topic, category=category, episode_no=episode_no,
                                       extra_instruction=extra_instruction)
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


# ── 2단계: TTS + 이미지 후보 생성 → Slack 이미지 게이트 (대본 승인 후) ──

def produce_images_task(job_id: str, topic: str, category: str = "직장", episode_no: int = None):
    """TTS-FIRST → 컷별 이미지 후보 생성 → Slack 이미지 선택 게이트.

    FAL_KEY 미설정 또는 SLACK_BOT_TOKEN 미설정 시 이미지 게이트를 건너뛰고
    selected_images.json 없이 produce_video_task를 바로 큐에 넣는다.
    """
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

        # 승인된 대본 로드
        script_path = os.path.join(tmp_dir, "script.json")
        with open(script_path, encoding="utf-8") as f:
            script = json.load(f)

        # 1. TTS (v5 §2.1: FIRST — 길이를 먼저 확정)
        _step(db, job, "generating_voice")
        voice_dir = os.path.join(tmp_dir, "voice")
        generate_pangi_voice(script_path, output_dir=voice_dir)

        # 2. TTS 길이 측정 → beat별 duration_sec 업데이트
        _step(db, job, "measuring_tts_duration")
        n_beats = len(script.get("beats", []))
        tts_durations = measure_beat_durations(voice_dir, n_beats)
        for i, beat in enumerate(script["beats"]):
            beat["tts_sec"] = round(tts_durations[i], 3)
            beat["duration_sec"] = round(tts_durations[i] + 0.4, 3)
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)

        # 3. 컷별 이미지 생성 (gpt-image-2) → Slack 이미지 게이트
        _step(db, job, "generating_cut_images")
        candidates_dir = os.path.join(tmp_dir, "candidates")
        n_candidates = int(os.getenv("IMAGE_CANDIDATES", "1"))
        has_any_candidate = False

        for i, beat in enumerate(script["beats"]):
            beat_name = beat.get("beat", "꿀팁3단")
            emotion = beat.get("emotion", "평온")
            paths = generate_cut_images(beat, i, candidates_dir, n_candidates=n_candidates)
            if paths:
                has_any_candidate = True
                for _ in paths:
                    record_cost("image")
                send_image_candidates(job_id, i, beat_name, emotion, paths, n_beats)
            else:
                # 이미지 생성 실패한 beat은 body_front.png 폴백으로 자동 선택
                print(f"[{job_id}] beat_{i} 이미지 생성 실패 — 레퍼런스 폴백 자동 선택")
                _save_selected_image(tmp_dir, i, os.getenv("PANGI_BODY", "assets/pang/base/body_front.png"))

        if has_any_candidate:
            job.current_step = "pending_image_approval"
            db.commit()
            print(f"[{job_id}] 이미지 후보 Slack 전송 완료 — 선택 대기")
        else:
            # 전체 실패 시 바로 영상 단계
            _enqueue_video(job_id, topic, category, episode_no)
            job.current_step = "image_gen_failed_fallback"
            db.commit()

    except Exception as e:
        _handle_failure(db, job, job_id, topic, category, episode_no, e,
                        "worker.tasks.produce_images_task")
        raise
    finally:
        db.close()


# ── 3단계: I2V + 렌더링 + 최종 게이트 (이미지 선택 완료 후) ──

def produce_video_task(job_id: str, topic: str, category: str = "직장", episode_no: int = None):
    """선택된 컷 이미지 → Kling I2V → FFmpeg 렌더 → Slack 최종 게이트."""
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

        # 승인된 대본 로드
        script_path = os.path.join(tmp_dir, "script.json")
        with open(script_path, encoding="utf-8") as f:
            script = json.load(f)
        tts_durations = [b.get("tts_sec", 5.0) for b in script.get("beats", [])]

        # 이미지 게이트에서 선택된 이미지 로드 (없으면 body_front.png 폴백)
        selected_images = _load_selected_images(tmp_dir)

        # 1. 배경 이미지 — Kling 클립(선택 이미지)이 전 컷 장면을 담으므로
        #    FAL_KEY 있으면 배경 별도 생성 불필요. 폴백 렌더(PIL/퍼펫)에서만 생성.
        bg_path = None
        if not os.getenv("FAL_KEY"):
            _step(db, job, "generating_background")
            bg_path = f"assets/bg/ep{episode_no:02d}_{category}.webp"
            if not os.path.exists(bg_path):
                generate_background(topic, category=category, output_path=bg_path)
                record_cost("background")

        # 2. Kling I2V 클립 (선택 이미지 사용, 무음, ⭐ 최대 비용)
        _step(db, job, "generating_clips")
        clips_dir = os.path.join(tmp_dir, "clips")
        if os.getenv("FAL_KEY"):
            clip_paths, clip_seconds = generate_all_clips(
                script, clips_dir,
                tts_durations=tts_durations,
                selected_images=selected_images,
            )
            for secs in clip_seconds:
                if secs > 0:
                    record_cost("i2v", seconds=secs)
        else:
            print(f"[{job_id}] FAL_KEY 미설정 — I2V 건너뛰고 폴백 렌더")

        # 3. 렌더링
        _step(db, job, "rendering")
        output_path = os.path.join(tmp_dir, "final.mp4")
        render_pangi_short(
            script_path=script_path,
            voice_dir=os.path.join(tmp_dir, "voice"),
            output_path=output_path,
            category=category,
            bg_path=bg_path,  # FAL_KEY 없는 폴백 시에만 값 있음
        )

        job.status = JobStatus.COMPLETED
        job.video_path = output_path
        job.vote_options = json.dumps(script.get("vote_options", []), ensure_ascii=False)
        job.current_step = "pending_approval"
        db.commit()

        send_approval_message(job_id, topic, output_path)
        print(f"[{job_id}] 제작 완료: {output_path}")

    except Exception as e:
        _handle_failure(db, job, job_id, topic, category, episode_no, e,
                        "worker.tasks.produce_video_task")
        raise
    finally:
        db.close()


# ── 컷 이미지 재생성 (특정 beat만) ──────────────────────────

def regen_cut_image_task(job_id: str, beat_idx: int, edit_prompt: str = ""):
    """특정 컷 이미지 재생성 → Slack 재전송. edit_prompt 있으면 수정 지시로 생성."""
    try:
        tmp_dir = _tmp_dir(job_id)
        script_path = os.path.join(tmp_dir, "script.json")
        with open(script_path, encoding="utf-8") as f:
            script = json.load(f)

        beats = script.get("beats", [])
        beat = beats[beat_idx]
        n_beats = len(beats)
        beat_name = beat.get("beat", f"컷{beat_idx + 1}")
        emotion = beat.get("emotion", "")

        candidates_dir = os.path.join(tmp_dir, "candidates")

        paths = generate_cut_images(
            beat, beat_idx, candidates_dir,
            n_candidates=1,
            edit_prompt=edit_prompt,
        )
        for _ in paths:
            record_cost("image")

        if paths:
            send_image_candidates(job_id, beat_idx, beat_name, emotion, paths, n_beats)
            label = f"수정({edit_prompt[:20]})" if edit_prompt else "재생성"
            print(f"[{job_id}] beat_{beat_idx} {label} 완료 → Slack 재전송")
        else:
            print(f"[{job_id}] beat_{beat_idx} 재생성 실패 — FAL_KEY 확인 필요")
    except Exception as e:
        print(f"[{job_id}] regen_cut_image_task 실패: {e}")


# ── 이미지 선택 상태 헬퍼 ─────────────────────────────────

def _selected_images_path(tmp_dir: str) -> str:
    return os.path.join(tmp_dir, "selected_images.json")


def _save_selected_image(tmp_dir: str, beat_idx: int, image_path: str):
    path = _selected_images_path(tmp_dir)
    data = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    data[str(beat_idx)] = image_path
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _load_selected_images(tmp_dir: str) -> dict:
    path = _selected_images_path(tmp_dir)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _all_images_selected(tmp_dir: str, n_beats: int) -> bool:
    data = _load_selected_images(tmp_dir)
    return all(str(i) in data for i in range(n_beats))


def _enqueue_video(job_id: str, topic: str, category: str, episode_no: int):
    from redis import Redis
    from rq import Queue
    redis_conn = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
    q = Queue("render_queue", connection=redis_conn, default_timeout=7200)
    q.enqueue("worker.tasks.produce_video_task", job_id, topic, category, episode_no)


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
    q = Queue("render_queue", connection=redis_conn, default_timeout=7200)
    q.enqueue_in(
        dt.timedelta(seconds=delay_sec),
        task,
        job_id, topic, category, episode_no,
    )
