"""
변주 엔진 — 후킹 타입 / 개그 톤 / 시작 감정 / 전개 모드를 LRU로 순환.

추적 대상:
  hook_type   : beat 1 후킹 패턴 (5종)
  tone        : 전체 개그 톤 (3종)
  hook_emotion: beat 1 감정 (13종 — 자신감 제외)
  dev_mode    : 중간 3비트 전개 방식 (4종 — 주제의 allowed_modes 안에서만 LRU)

추적 제외:
  beat 6 마무리 감정 → OUTRO_EMOTION 고정 (브랜드 앵커)
"""
import json
import os

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TRACKER_PATH = os.path.join(_BASE_DIR, "data", "variation_tracker.json")

# ── 풀 정의 ──────────────────────────────────────────────────
HOOK_TYPES = ["질문형", "선언형", "도발형", "지목형", "예고형"]
COMEDY_TONES = ["과장 몰아치기", "진지한 척", "자조"]
HOOK_EMOTIONS = [
    "평온", "기쁨", "신남", "설렘", "뿌듯함",
    "슬픔", "분노", "무서움", "충격", "심술", "멍함", "과부하", "재부팅",
]
DEV_MODES = ["코칭", "유형", "상상현실", "공감폭발"]
OUTRO_EMOTION = "자신감"  # beat 6 고정 — 로테이션 대상 아님

# 트래커가 보관할 최대 이력 수 (가장 큰 풀 크기 = 13)
_MAX_HISTORY = max(len(HOOK_TYPES), len(COMEDY_TONES), len(HOOK_EMOTIONS), len(DEV_MODES))

# 후킹 타입별 GPT 지시어
_HOOK_TYPE_DESC = {
    "질문형": "시청자에게 직접 묻는 형식으로 시작 ('~한 적 있지?' / '~이라면?')",
    "선언형": "팡이가 본심을 단정적으로 선언 ('이거 다 알면서 하는 거야')",
    "도발형": "도전적·자극적 한 줄로 긴장감 유발 ('설마 아직도 모르는 거야?')",
    "지목형": "특정 상황에 처한 사람을 직접 지목 ('지금 이러고 있는 사람 손들어봐')",
    "예고형": "이번 편에서 알려줄 것을 미리 예고 ('오늘 이거 알면 인생 달라져')",
}

_TONE_DESC = {
    "과장 몰아치기": "감정·상황을 극단적으로 과장해 웃음 유발 — 단, 한 대사에 비유·이미지는 1개만. 과장의 강도를 높이되 비유를 겹치지 말 것",
    "진지한 척": "엄청 심각한 표정·말투로 시작했다가 허당 결론",
    "자조": "팡이 자신이 당했거나 실패한 척하며 공감 유도",
}

_DEV_MODE_DESC = {
    "코칭":     "팡이 공범 어조로 꼼수·해법 3개를 하나씩 코치",
    "유형":     "주제 관련 유형·패턴 3개를 하나씩 지목·폭로",
    "상상현실": "망상·기대 → 현실 충격 → 여운·합리화의 감정 아크",
    "공감폭발": "'이럴 때 이러지' 순간 포착 ×3, 팡이가 공범으로 편들기",
}


# ── 트래커 IO ─────────────────────────────────────────────────

def _load() -> list[dict]:
    if not os.path.exists(_TRACKER_PATH):
        return []
    with open(_TRACKER_PATH, encoding="utf-8") as f:
        return json.load(f).get("recent", [])


def _save(recent: list[dict]):
    os.makedirs(os.path.dirname(_TRACKER_PATH), exist_ok=True)
    with open(_TRACKER_PATH, "w", encoding="utf-8") as f:
        json.dump({"recent": recent[-_MAX_HISTORY:]}, f, ensure_ascii=False, indent=2)


# ── LRU 선택 ─────────────────────────────────────────────────

def _lru_pick(pool: list, recent: list[dict], key: str) -> str:
    """pool 중 recent에서 가장 오래전에 쓴 항목 반환. 미사용 항목은 ep=0 취급.

    dict 컴프리헨션 대신 max 누산 — recent 순서에 무관하게 항상 올바른 최신 ep를 기록.
    """
    last_used: dict = {}
    for r in recent:
        if key in r:
            last_used[r[key]] = max(last_used.get(r[key], 0), r["ep"])
    return min(pool, key=lambda x: last_used.get(x, 0))


# ── 공개 API ──────────────────────────────────────────────────

def pick_variation(allowed_modes: list[str] = None) -> dict:
    """이번 에피소드에 쓸 변주 조합 반환.

    allowed_modes: 주제가 허용하는 전개 모드 목록. None이면 전체 DEV_MODES.
                   허용 모드 안에서만 LRU — 미스매치 방지.
    """
    recent = _load()
    hook_type    = _lru_pick(HOOK_TYPES,                     recent, "hook_type")
    tone         = _lru_pick(COMEDY_TONES,                   recent, "tone")
    hook_emotion = _lru_pick(HOOK_EMOTIONS,                  recent, "hook_emotion")
    dev_mode     = _lru_pick(allowed_modes or DEV_MODES,     recent, "dev_mode")
    return {
        "hook_type":    hook_type,
        "tone":         tone,
        "hook_emotion": hook_emotion,
        "dev_mode":     dev_mode,
    }


def record_episode(ep: int, hook_type: str, tone: str, hook_emotion: str, dev_mode: str):
    """에피소드 완료 후 이력에 기록."""
    recent = _load()
    recent.append({
        "ep": ep,
        "hook_type": hook_type,
        "tone": tone,
        "hook_emotion": hook_emotion,
        "dev_mode": dev_mode,
    })
    _save(recent)


def build_variation_prompt(variation: dict) -> str:
    """시스템 프롬프트에 삽입할 변주 지시 블록 반환."""
    ht = variation["hook_type"]
    tn = variation["tone"]
    he = variation["hook_emotion"]
    dm = variation["dev_mode"]

    others = [e for e in HOOK_EMOTIONS if e != he]
    available = f"{he} (우선 사용), 또는 {', '.join(others)}"

    return f"""
[이번 에피소드 변주 지정 — 반드시 준수]
- 후킹(beat 1) 타입: {ht} — {_HOOK_TYPE_DESC[ht]}
- 개그 톤 (전체): {tn} — {_TONE_DESC[tn]}
- beat 1 감정: {available}
- 전개 모드 (beat 3·4·5): {dm} — {_DEV_MODE_DESC[dm]}
- beat 6(마무리) 감정: {OUTRO_EMOTION} 고정 (브랜드 앵커 — 변경 금지)

[meme_ref — 모든 beat에 선택 필드]
감정 전환이 있는 beat에 우선 배치. 안전 버전만 허용: 포즈·상황·짧은 대사·오리지널 동작 (실제 음원·영상 참조 ✗).
예) "박하사탕 돌아갈래 포즈 — 고개 뒤로 돌리며 멍하게 서 있는 동작"
meme_ref가 없으면 해당 필드 생략 가능."""
