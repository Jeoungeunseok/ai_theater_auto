"""
비용 가드레일 — 일일 OpenAI 지출 추적 + 임계치 초과 시 큐 일시 정지
Redis 키:
  daily_cost:{YYYY-MM-DD}  → float (달러)
  queue_paused             → "1" | (없음)
"""
import os
import datetime
from redis import Redis
from dotenv import load_dotenv

load_dotenv()

_DAILY_LIMIT = float(os.getenv("DAILY_COST_LIMIT", "1.0"))
# v4 §3.5: 에피소드(job)당 재생성 상한 — 리롤 폭주(곧 비용) 방지
_MAX_REGEN = int(os.getenv("MAX_REGEN_PER_EPISODE", "5"))

# 추정 단가 (달러/call)
_COST_PER_CALL = {
    "script": 0.003,    # gpt-4o-mini 약 2000 input + 500 output tokens
    "background": 0.053, # gpt-image-2 medium
    "image": 0.053,     # 컷별 후보 이미지 (gpt-image-2 medium)
    "i2v": 0.112,       # ⭐ Kling v3/pro — $0.112/초 (초 단위로 곱해서 사용)
    "thumbnail": 0.053,  # gpt-image-2 medium (1024x1024)
}


def _redis() -> Redis:
    return Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)


def _today_key() -> str:
    return f"daily_cost:{datetime.date.today().isoformat()}"


# ── 비용 기록 ─────────────────────────────────────────────

def record_cost(call_type: str, seconds: float = 1.0):
    """API 호출 후 비용 기록. i2v는 seconds에 실제 클립 초 수 전달."""
    cost = _COST_PER_CALL.get(call_type, 0.0) * seconds
    if cost <= 0:
        return
    r = _redis()
    key = _today_key()
    r.incrbyfloat(key, cost)
    r.expire(key, 86400 * 2)  # 2일 후 자동 삭제

    total = float(r.get(key) or 0)
    if total >= _DAILY_LIMIT:
        r.set("queue_paused", "1")
        print(f"[COST] 일일 한도 초과 ({total:.3f}$ / {_DAILY_LIMIT}$) — 큐 일시 정지")


# ── 큐 정지 확인 ──────────────────────────────────────────

def is_queue_paused() -> bool:
    r = _redis()
    return r.exists("queue_paused") == 1


def resume_queue():
    """임계치 초과로 정지된 큐를 수동 재개."""
    _redis().delete("queue_paused")
    print("[COST] 큐 재개")


# ── 에피소드당 재생성 상한 (v4 §3.5) ─────────────────────

def _regen_key(job_id: str) -> str:
    return f"regen_count:{job_id}"


def incr_regen(job_id: str) -> int:
    """재생성 1회 기록 → 누적 횟수 반환."""
    r = _redis()
    key = _regen_key(job_id)
    n = r.incr(key)
    r.expire(key, 86400 * 7)  # 7일 후 자동 삭제
    return int(n)


def get_regen_count(job_id: str) -> int:
    return int(_redis().get(_regen_key(job_id)) or 0)


def regen_limit_reached(job_id: str) -> bool:
    """이번 에피소드의 재생성 상한 도달 여부."""
    return get_regen_count(job_id) >= _MAX_REGEN


def regen_limit() -> int:
    return _MAX_REGEN


# ── 오늘 사용량 조회 ──────────────────────────────────────

def get_today_cost() -> float:
    r = _redis()
    return float(r.get(_today_key()) or 0)


# ── 자정 리셋 (cron에서 호출) ─────────────────────────────

def midnight_reset():
    """매일 자정 비용 초과 플래그 초기화."""
    today_cost = get_today_cost()
    r = _redis()
    r.delete("queue_paused")
    print(f"[COST] 어제 총 비용: ${today_cost:.3f} — 큐 재개")


if __name__ == "__main__":
    print(f"오늘 누적 비용: ${get_today_cost():.4f} / 한도 ${_DAILY_LIMIT}")
    print(f"큐 정지 상태: {is_queue_paused()}")
