import os
import json
import yaml
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_CATEGORY_FILE = {
    "직장": "work.yaml",
    "욕망": "desire.yaml",
    "부부": "couple.yaml",
    "일상": "daily.yaml",
}


def _load_persona() -> dict:
    path = os.path.join(_BASE_DIR, "prompts", "pangi_persona.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_category(category: str) -> dict:
    filename = _CATEGORY_FILE.get(category)
    if not filename:
        return {}
    path = os.path.join(_BASE_DIR, "prompts", filename)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_system_prompt(persona: dict, category_cfg: dict) -> str:
    tone_rules = "\n".join(f"- {t}" for t in persona["personality"]["tone"])
    forbidden = "\n".join(f"- {t}" for t in persona["personality"]["forbidden"])
    emotions = ", ".join(persona["emotions"].keys())

    # 카테고리별 추가 톤 규칙
    extra_tone = ""
    if category_cfg.get("tone_additions"):
        extras = "\n".join(f"- {t}" for t in category_cfg["tone_additions"])
        extra_tone = f"\n[{category_cfg.get('category', '')} 카테고리 특화 톤]\n{extras}"

    extra_forbidden = ""
    if category_cfg.get("forbidden_additions"):
        fb = "\n".join(f"- {t}" for t in category_cfg["forbidden_additions"])
        extra_forbidden = f"\n[추가 금지 사항]\n{fb}"

    # 예시 후킹
    hook_examples = ""
    if category_cfg.get("example_hooks"):
        examples = "\n".join(f'  · "{h}"' for h in category_cfg["example_hooks"])
        hook_examples = f"\n[후킹 예시 (이 스타일로)]\n{examples}"

    return f"""당신은 와이파이 의인화 캐릭터 팡이의 전담 대본 작가입니다.

[팡이 기본 톤 규칙]
{tone_rules}
{extra_tone}

[절대 금지]
{forbidden}
{extra_forbidden}

[사용 가능한 감정] {emotions}

[에피소드 포맷 — 총 약 30초]
beat 1 "후킹"    (3초): 시청자가 멈추게 만드는 도발적 본심 선언 한 줄
beat 2 "본심수신" (2초): 팡이가 본심 주파수 수신 — 안테나 번쩍 멘트
beat 3 "꿀팁1"   (7초): 능청 코칭 첫 번째
beat 4 "꿀팁2"   (7초): 능청 코칭 두 번째
beat 5 "꿀팁3"   (6초): 능청 코칭 세 번째
beat 6 "마무리"  (5초): 공범 윙크 + 다음 본심 투표 CTA
{hook_examples}

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "episode_no": <int>,
  "category": "<카테고리>",
  "topic": "<주제>",
  "beats": [
    {{"beat": "후킹",    "emotion": "<감정>", "dialogue": "<대사>", "duration_sec": 3}},
    {{"beat": "본심수신","emotion": "<감정>", "dialogue": "<대사>", "duration_sec": 2}},
    {{"beat": "꿀팁1",  "emotion": "<감정>", "dialogue": "<대사>", "duration_sec": 7}},
    {{"beat": "꿀팁2",  "emotion": "<감정>", "dialogue": "<대사>", "duration_sec": 7}},
    {{"beat": "꿀팁3",  "emotion": "<감정>", "dialogue": "<대사>", "duration_sec": 6}},
    {{"beat": "마무리", "emotion": "<감정>", "dialogue": "<대사>", "duration_sec": 5}}
  ],
  "vote_options": ["<다음 주제 후보 A>", "<다음 주제 후보 B>"]
}}"""


def generate_pangi_script(topic: str, category: str = "직장", episode_no: int = 1) -> dict:
    persona = _load_persona()
    category_cfg = _load_category(category)
    system_prompt = _build_system_prompt(persona, category_cfg)

    user_prompt = (
        f"카테고리: {category}\n"
        f"주제: {topic}\n"
        f"에피소드 번호: {episode_no}\n\n"
        "위 주제로 팡이 에피소드 대본을 JSON으로 작성해줘."
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    return json.loads(response.choices[0].message.content)


if __name__ == "__main__":
    script = generate_pangi_script(
        topic="상사 몰래 쉬는 법",
        category="직장",
        episode_no=1,
    )
    os.makedirs("tmp/aitheater", exist_ok=True)
    out = "tmp/aitheater/script.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)
    print(f"대본 생성 완료: {out}")
    for b in script.get("beats", []):
        print(f"  [{b['beat']}] {b['emotion']} — {b['dialogue'][:30]}...")
