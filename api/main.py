import os
import json
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
from redis import Redis
from rq import Queue
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Job, JobStatus, Submission
from api.slack import verify_slack_signature
from scripts.topic_engine import add_submission
from scripts.daily_cost import incr_regen, regen_limit_reached, regen_limit
from worker.slack_notifier import (
    send_regen_limit_warning, update_image_selected, update_image_regenerating,
    update_thumbnail_regenerating,
)

app = FastAPI(title="팡이 API")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_conn = Redis.from_url(REDIS_URL)
render_queue = Queue("render_queue", connection=redis_conn, default_timeout=7200)  # I2V 최대 2시간
upload_queue = Queue("upload_queue", connection=redis_conn, default_timeout=3600)


def _slack_client() -> WebClient | None:
    token = os.getenv("SLACK_BOT_TOKEN")
    return WebClient(token=token) if token else None


class JobCreate(BaseModel):
    topic: str
    category: str = "직장"
    episode_no: Optional[int] = None


class SubmissionCreate(BaseModel):
    raw_text: str
    consent: bool  # 반드시 True여야 접수


class JobResponse(BaseModel):
    job_id: str
    status: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/submissions")
async def create_submission(body: SubmissionCreate, db: Session = Depends(get_db)):
    """시청자 제보 접수 — 동의 필수, 개인정보 자동 익명화."""
    if not body.consent:
        raise HTTPException(status_code=400, detail="동의 없이 제보 불가")
    add_submission(body.raw_text, consent=True, db=db)
    return {"ok": True, "message": "제보해주셔서 감사합니다! 팡이가 까발려드릴게요."}


@app.post("/jobs", response_model=JobResponse)
async def create_job(body: JobCreate, db: Session = Depends(get_db)):
    job_id = uuid.uuid4()
    new_job = Job(
        id=job_id,
        topic=body.topic,
        category=body.category,
        episode_no=body.episode_no,
        status=JobStatus.PENDING,
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    # v4 §3.3: 가장 싼 단계(대본)부터 게이트 — 비싼 I2V는 대본 승인 후에만
    render_queue.enqueue(
        "worker.tasks.create_script_task",
        str(job_id),
        body.topic,
        body.category,
        body.episode_no,
    )
    return {"job_id": str(job_id), "status": "PENDING"}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": str(job.id),
        "status": job.status.value,
        "current_step": job.current_step,
        "category": job.category,
        "episode_no": job.episode_no,
        "video_path": job.video_path,
        "youtube_id": job.youtube_id,
        "retry_count": job.retry_count,
        "error_log": job.error_log,
    }


@app.post("/slack/commands")
async def slack_commands(request: Request):
    await verify_slack_signature(request)
    form_data = await request.form()
    command = form_data.get("command", "")
    trigger_id = form_data.get("trigger_id", "")

    if command == "/팡이":
        _open_new_job_modal(trigger_id)
    return {"response_type": "ephemeral", "text": "잠시만요..."}


@app.post("/slack/actions")
async def slack_actions(request: Request, db: Session = Depends(get_db)):
    await verify_slack_signature(request)

    form_data = await request.form()
    payload = json.loads(form_data["payload"])
    payload_type = payload.get("type")

    # ── 모달 제출 ──────────────────────────────────────────
    if payload_type == "view_submission":
        callback_id = payload["view"].get("callback_id")

        if callback_id == "regen_script_modal":
            values = payload["view"]["state"]["values"]
            job_id = payload["view"]["private_metadata"]
            extra = values.get("instruction_block", {}).get("instruction_input", {}).get("value", "") or ""
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.current_step = "regenerating_script"
                db.commit()
                render_queue.enqueue(
                    "worker.tasks.create_script_task",
                    str(job_id), job.topic, job.category, job.episode_no, extra,
                )
            return {}

        if callback_id == "new_job_modal":
            values = payload["view"]["state"]["values"]
            topic = values.get("topic_block", {}).get("topic_input", {}).get("value", "")
            category = (
                values.get("category_block", {})
                .get("category_select", {})
                .get("selected_option", {})
                .get("value", "직장")
            )
            job_id = uuid.uuid4()
            new_job = Job(id=job_id, topic=topic, category=category, status=JobStatus.PENDING)
            db.add(new_job)
            db.commit()
            render_queue.enqueue("worker.tasks.create_script_task", str(job_id), topic, category, None)
            print(f"[Slack /팡이] 잡 생성 완료 — {topic} ({category})")
            return {}

        if callback_id == "edit_image_modal":
            meta = payload["view"]["private_metadata"].split("|", 3)
            job_id_m, beat_idx_str, channel_id, message_ts = meta
            beat_idx = int(beat_idx_str)
            edit_prompt = (
                payload["view"]["state"]["values"]
                .get("edit_block", {})
                .get("edit_input", {})
                .get("value", "") or ""
            )
            # 기존 메시지 → "수정 중..." 교체
            n_beats = 6
            script_path = os.path.join(f"tmp/aitheater/{job_id_m}", "script.json")
            if os.path.exists(script_path):
                with open(script_path, encoding="utf-8") as f:
                    n_beats = len(json.load(f).get("beats", []))
            update_image_regenerating(channel_id, message_ts, beat_idx, n_beats)
            render_queue.enqueue("worker.tasks.regen_cut_image_task", job_id_m, beat_idx, edit_prompt)
            return {}

        if callback_id == "reject_reason_modal":
            job_id = payload["view"]["private_metadata"]
            reason = (
                payload["view"]["state"]["values"]
                .get("reason_block", {})
                .get("reason_input", {})
                .get("value", "")
            )
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = JobStatus.FAILED
                job.error_log = f"반려 사유: {reason}"
                db.commit()
        return {}  # Slack은 view_submission에 빈 응답 기대

    # ── 버튼 액션 ──────────────────────────────────────────
    action = payload["actions"][0]
    action_id = action["action_id"]
    trigger_id = payload.get("trigger_id")
    raw_value = action["value"]

    # select_image_, edit_image_ 액션은 value가 "{job_id}|..." 형태
    if action_id.startswith("select_image_") or action_id.startswith("edit_image_"):
        job_id = raw_value.split("|", 1)[0]
    else:
        job_id = raw_value

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return {"ok": False, "error": "Job not found"}

    # ── 대본 게이트 (v4 §3.3, 가장 싼 단계) ────────────────
    if action_id == "approve_script":
        # 대본 승인 → TTS + 이미지 후보 생성 → 이미지 게이트
        job.current_step = "script_approved"
        db.commit()
        render_queue.enqueue(
            "worker.tasks.produce_images_task",
            str(job_id),
            job.topic,
            job.category,
            job.episode_no,
        )
        return {"ok": True}

    elif action_id == "regenerate_script":
        if not _guard_regen(job):
            return {"ok": True}
        _open_regen_script_modal(trigger_id, job_id)
        return {"ok": True}

    # ── 이미지 게이트 — 컷 선택 ───────────────────────────────
    if action_id.startswith("select_image_"):
        # value: "{job_id}|{beat_idx}|{image_path}"
        parts = raw_value.split("|", 2)
        if len(parts) != 3:
            return {"ok": False, "error": "Invalid select_image value"}
        _, beat_idx_str, image_path = parts
        beat_idx = int(beat_idx_str)

        tmp_dir = f"tmp/aitheater/{job_id}"
        script_path = os.path.join(tmp_dir, "script.json")
        if not os.path.exists(script_path):
            return {"ok": False, "error": "script.json not found"}

        with open(script_path, encoding="utf-8") as f:
            script = json.load(f)
        n_beats = len(script.get("beats", []))

        # 선택 저장
        selected_path = os.path.join(tmp_dir, "selected_images.json")
        selected = {}
        if os.path.exists(selected_path):
            with open(selected_path, encoding="utf-8") as f:
                selected = json.load(f)
        selected[str(beat_idx)] = image_path
        with open(selected_path, "w", encoding="utf-8") as f:
            json.dump(selected, f, ensure_ascii=False)

        # 선택 버튼 → '✅ 선택 완료' 메시지로 교체
        beat_info = script.get("beats", [])[beat_idx] if beat_idx < len(script.get("beats", [])) else {}
        update_image_selected(
            channel_id=payload.get("channel", {}).get("id", ""),
            message_ts=payload.get("message", {}).get("ts", ""),
            beat_idx=beat_idx,
            beat_name=beat_info.get("beat", f"컷{beat_idx + 1}"),
            emotion=beat_info.get("emotion", ""),
            candidate_no=1,
            n_beats=n_beats,
        )

        # 모든 beat 선택 완료 시 → I2V·렌더 단계 시작 (중복 투입 방지)
        if all(str(i) in selected for i in range(n_beats)) and job.current_step != "all_images_selected":
            job.current_step = "all_images_selected"
            db.commit()
            render_queue.enqueue(
                "worker.tasks.produce_video_task",
                str(job_id),
                job.topic,
                job.category,
                job.episode_no,
            )
            print(f"[{job_id}] 전체 컷 이미지 선택 완료 → I2V 큐 투입")
        else:
            remaining = n_beats - len(selected)
            print(f"[{job_id}] beat_{beat_idx} 선택 완료 ({remaining}컷 남음)")
            db.commit()

        return {"ok": True}

    # ── 컷 이미지 수정 (프롬프트 입력 모달) ──────────────────
    if action_id.startswith("edit_image_"):
        beat_idx = int(action_id.split("_b", 1)[1])
        channel_id = payload.get("channel", {}).get("id", "")
        message_ts = payload.get("message", {}).get("ts", "")
        _open_edit_image_modal(trigger_id, job_id, beat_idx, channel_id, message_ts)
        return {"ok": True}

    # ── 최종 영상 게이트 ───────────────────────────────────
    if action_id == "approve_video":
        job.current_step = "approved"
        upload_queue.enqueue("worker.upload_tasks.generate_thumbnail_task", job_id)

    elif action_id == "reject_video":
        # 모달 열어서 사유 입력받기
        _open_reject_modal(trigger_id, job_id)
        return {"ok": True}  # 모달 오픈 후 즉시 응답

    elif action_id == "regenerate_video":
        if not _guard_regen(job):
            return {"ok": True}
        job.status = JobStatus.PENDING
        job.current_step = "regenerating"
        job.retry_count = 0
        job.error_log = None
        # 이미지부터 다시 — 이전 selected_images.json 삭제해서 선택 초기화
        selected_path = os.path.join(f"tmp/aitheater/{job_id}", "selected_images.json")
        if os.path.exists(selected_path):
            os.remove(selected_path)
        render_queue.enqueue(
            "worker.tasks.produce_images_task",
            str(job_id),
            job.topic,
            job.category,
            job.episode_no,
        )

    # ── 썸네일 게이트 ─────────────────────────────────────
    elif action_id == "approve_thumbnail":
        job.current_step = "thumbnail_approved"
        db.commit()
        upload_queue.enqueue("worker.upload_tasks.upload_video_task", job_id)
        return {"ok": True}

    elif action_id == "regenerate_thumbnail":
        update_thumbnail_regenerating(
            channel_id=payload.get("channel", {}).get("id", ""),
            message_ts=payload.get("message", {}).get("ts", ""),
        )
        job.current_step = "regenerating_thumbnail"
        db.commit()
        upload_queue.enqueue("worker.upload_tasks.generate_thumbnail_task", job_id)
        return {"ok": True}

    db.commit()
    return {"ok": True}


def _guard_regen(job) -> bool:
    """v4 §3.5: 재생성 상한 가드. 한도 도달 시 Slack 경고 후 False(차단)."""
    job_id = str(job.id)
    if regen_limit_reached(job_id):
        send_regen_limit_warning(job_id, job.topic, regen_limit())
        return False
    incr_regen(job_id)
    return True


def _open_new_job_modal(trigger_id: str):
    """슬래시 커맨드 /팡이 → 주제·카테고리 입력 모달."""
    client = _slack_client()
    if not client or not trigger_id:
        return
    try:
        client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": "new_job_modal",
                "title": {"type": "plain_text", "text": "팡이 에피소드 생성"},
                "submit": {"type": "plain_text", "text": "생성 시작"},
                "close": {"type": "plain_text", "text": "취소"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "topic_block",
                        "label": {"type": "plain_text", "text": "주제"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "topic_input",
                            "placeholder": {"type": "plain_text", "text": "예: 상사 몰래 쉬는 법"},
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "category_block",
                        "label": {"type": "plain_text", "text": "카테고리"},
                        "element": {
                            "type": "static_select",
                            "action_id": "category_select",
                            "placeholder": {"type": "plain_text", "text": "카테고리 선택"},
                            "initial_option": {"text": {"type": "plain_text", "text": "직장"}, "value": "직장"},
                            "options": [
                                {"text": {"type": "plain_text", "text": "직장"}, "value": "직장"},
                                {"text": {"type": "plain_text", "text": "욕망"}, "value": "욕망"},
                                {"text": {"type": "plain_text", "text": "부부"}, "value": "부부"},
                                {"text": {"type": "plain_text", "text": "일상"}, "value": "일상"},
                            ],
                        },
                    },
                ],
            },
        )
    except SlackApiError as e:
        print(f"[WARN] new_job 모달 오픈 실패: {e}")


def _open_regen_script_modal(trigger_id: str, job_id: str):
    """대본 재생성 — 추가 지시 입력 모달."""
    client = _slack_client()
    if not client or not trigger_id:
        return
    try:
        client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": "regen_script_modal",
                "private_metadata": job_id,
                "title": {"type": "plain_text", "text": "대본 재생성"},
                "submit": {"type": "plain_text", "text": "재생성"},
                "close": {"type": "plain_text", "text": "취소"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "instruction_block",
                        "optional": True,
                        "label": {"type": "plain_text", "text": "추가 요청 (선택)"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "instruction_input",
                            "multiline": True,
                            "placeholder": {
                                "type": "plain_text",
                                "text": "예: 더 웃기게, 후킹 더 강하게, 톤 가볍게...",
                            },
                        },
                    }
                ],
            },
        )
    except SlackApiError as e:
        print(f"[WARN] 재생성 모달 오픈 실패: {e}")


def _open_edit_image_modal(trigger_id: str, job_id: str, beat_idx: int,
                           channel_id: str, message_ts: str):
    """이미지 수정 지시 입력 모달."""
    client = _slack_client()
    if not client or not trigger_id:
        return
    try:
        client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": "edit_image_modal",
                "private_metadata": f"{job_id}|{beat_idx}|{channel_id}|{message_ts}",
                "title": {"type": "plain_text", "text": "이미지 수정"},
                "submit": {"type": "plain_text", "text": "수정"},
                "close": {"type": "plain_text", "text": "취소"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "edit_block",
                        "label": {"type": "plain_text", "text": "수정 요청"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "edit_input",
                            "multiline": True,
                            "placeholder": {
                                "type": "plain_text",
                                "text": "예: 배경을 사무실로 바꿔줘, 표정을 더 강하게, 더 밝고 귀엽게...",
                            },
                        },
                    }
                ],
            },
        )
    except SlackApiError as e:
        print(f"[WARN] 이미지 수정 모달 오픈 실패: {e}")


def _open_reject_modal(trigger_id: str, job_id: str):
    """반려 사유 입력 모달 오픈."""
    client = _slack_client()
    if not client or not trigger_id:
        return
    try:
        client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": "reject_reason_modal",
                "private_metadata": job_id,
                "title": {"type": "plain_text", "text": "반려 사유"},
                "submit": {"type": "plain_text", "text": "확인"},
                "close": {"type": "plain_text", "text": "취소"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "reason_block",
                        "label": {"type": "plain_text", "text": "반려 사유를 입력해주세요"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "reason_input",
                            "multiline": True,
                            "placeholder": {
                                "type": "plain_text",
                                "text": "예: 후킹이 약함, 톤이 너무 무거움...",
                            },
                        },
                    }
                ],
            },
        )
    except SlackApiError as e:
        print(f"[WARN] 반려 모달 오픈 실패: {e}")
