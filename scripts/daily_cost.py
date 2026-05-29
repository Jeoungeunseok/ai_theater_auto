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

# gpt-4o-mini 추정 단가 (달러/call)
_COST_PER_CALL = {
    "script": 0.003,    # 약 2000 input + 500 output tokens
    "background": 0.053, # gpt-image-2 medium
    "thumbnail": 0.0,   # Pillow 로컬 생성
}


def _redis() -> Redis:
    return Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)


def _today_key() -> str:
    return f"daily_cost:{datetime.date.today().isoformat()}"


# ── 비용 기록 ─────────────────────────────────────────────

def record_cost(call_type: str):
    """API 호출 후 비용 기록. call_type: script | background | thumbnail"""
    cost = _COST_PER_CALL.get(call_type, 0.0)
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
