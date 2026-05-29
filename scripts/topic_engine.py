"""
소재 엔진 — 4단 소스 우선순위:
  1. 투표 최다 득표
  2. 시청자 제보 (submissions)
  3. 아키타입 뱅크 (archetype_bank.yaml 미사용 항목)
  4. AI 오리지널
"""
import os
import re
import json
import random
import yaml
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ARCHETYPE_PATH = os.path.join(_BASE_DIR, "prompts", "archetype_bank.yaml")

_PII_PATTERN = re.compile(
    r"\b(\d{2,3}-\d{3,4}-\d{4}|[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b"
)


# ── 시청자 제보 ───────────────────────────────────────────

def _anonymize(text: str) -> str:
    """전화번호·이메일 등 개인식별정보 제거."""
    return _PII_PATTERN.sub("[익명]", text).strip()


def add_submission(raw_text: str, consent: bool, db) -> bool:
    """제보 DB 저장. consent=False면 거부."""
    if not consent:
        return False
    from db.models import Submission
    sub = Submission(raw_text=_anonymize(raw_text), consent=True, status="pending")
    db.add(sub)
    db.commit()
    return True


# ── 아키타입 뱅크 ─────────────────────────────────────────

def _load_archetypes() -> dict:
    with open(_ARCHETYPE_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _mark_archetype_used(archetype_id: str):
    """사용된 아키타입을 yaml에서 status: used로 업데이트."""
    data = _load_archetypes()
    for category_items in data.values():
        for item in category_items:
            if item.get("id") == archetype_id:
                item["status"] = "used"
    with open(_ARCHETYPE_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)


def pick_archetype_topic(category: str) -> dict | None:
    """아키타입 뱅크에서 미사용 항목을 랜덤 선택."""
    data = _load_archetypes()
    items = data.get(category, [])
    pending = [i for i in items if i.get("status") == "pending"]
    if not pending:
        return None
    chosen = random.choice(pending)
    _mark_archetype_used(chosen["id"])
    return {
        "topic": chosen["topic"],
        "source": "archetype",
        "hook": random.choice(chosen.get("hooks", [])),
        "tips": chosen.get("tips", []),
        "archetype_id": chosen["id"],
    }


# ── 트렌드 마이닝 ─────────────────────────────────────────

def mine_trend_topic(category: str) -> dict:
    """GPT로 현재 트렌드 기반 본심 주제 추출."""
    prompt = (
        f"한국에서 지금 '{category}' 카테고리와 관련해 사람들이 SNS나 커뮤니티에서 "
        f"공감하거나 하소연하는 '본심 상황'을 1가지 찾아줘. "
        f"실제 원문이 아닌 상황 유형만 추출해. "
        f"JSON으로: {{\"topic\": \"...\", \"reason\": \"...\"}}"
    )
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)
    return {
        "topic": data.get("topic", ""),
        "source": "trend",
        "context": data.get("reason", ""),
    }


# ── AI 오리지널 ───────────────────────────────────────────

def generate_ai_original(category: str, context: str = "") -> dict:
    """GPT가 완전 새 사연 생성 — 저작권·원본 없음."""
    prompt = (
        f"팡이 채널용 '{category}' 카테고리 본심 에피소드 주제를 완전히 새로 만들어줘. "
        f"{'참고 맥락: ' + context if context else ''} "
        f"실존 인물·사건 참조 없이 보편적 공감 상황으로. "
        f"JSON: {{\"topic\": \"...\", \"hook\": \"...\"}}"
    )
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)
    return {
        "topic": data.get("topic", ""),
        "source": "ai_original",
        "hook": data.get("hook", ""),
    }


# ── 통합 선택기 ───────────────────────────────────────────

def pick_next_topic(category: str, db, vote_winner: str = "") -> dict:
    """
    우선순위:
      1. 투표 최다 득표 (vote_winner 전달 시)
      2. 시청자 제보 (pending submissions)
      3. 아키타입 뱅크 (미사용 항목)
      4. AI 오리지널
    """
    # 1. 투표 우승 주제
    if vote_winner:
        return {"topic": vote_winner, "source": "vote"}

    # 2. 시청자 제보
    from db.models import Submission
    sub = db.query(Submission).filter(Submission.status == "pending").first()
    if sub:
        sub.status = "processing"
        db.commit()
        return {"topic": sub.raw_text[:50], "source": "submission", "submission_id": sub.id}

    # 3. 아키타입 뱅크
    archetype = pick_archetype_topic(category)
    if archetype:
        return archetype

    # 4. AI 오리지널 (fallback)
    return generate_ai_original(category)
