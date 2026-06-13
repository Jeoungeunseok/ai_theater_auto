import os
import json
import yaml
from openai import OpenAI
from dotenv import load_dotenv
from scripts.variation_engine import pick_variation, record_episode, build_variation_prompt, OUTRO_EMOTION

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_CATEGORY_FILE = {
    "직장": "work.yaml",
    "욕망": "desire.yaml",
    "부부": "couple.yaml",
    "일상": "daily.yaml",
}

# 전개 모드별 beat 3·4·5 설명 — 시스템 프롬프트 beat 포맷 섹션에 삽입
_DEV_MODE_BEAT_DESC = {
    "코칭": [
        "꼼수·해법 첫 번째 — 팡이 공범 어조로 임팩트 있게 하나만. 독립 완결 문장.",
        "꼼수·해법 두 번째 — 앞과 자연스럽게 이어지되 독립적 문장.",
        "꼼수·해법 세 번째 — 반전 또는 핵심 하이라이트. 완결.",
    ],
    "유형": [
        "1번째 유형 지목 — '이런 사람/상황 있잖아' 공범 어조. 임팩트 있게.",
        "2번째 유형 지목 — 다른 각도, 독립적 문장.",
        "3번째 유형 — 반전·웃음 포인트. 완결.",
    ],
    "상상현실": [
        "망상·기대 — 설렘·과장으로 시작. 독립 완결 문장.",
        "현실 충격 — 앞 beat와 대비, 반전·허당 구조.",
        "여운·합리화 — 팡이가 공범으로 편들기. 완결.",
    ],
    "공감폭발": [
        "'이럴 때 이러지' 첫 번째 순간 — 팡이가 '나도 그래' 편들며 독립 완결.",
        "두 번째 공감 순간 — 다른 각도, 독립적 문장.",
        "세 번째 공감 순간 — 반전 또는 핵심 공감. 완결.",
    ],
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


def _build_system_prompt(persona: dict, variation: dict) -> str:
    tone_rules = "\n".join(f"- {t}" for t in persona["personality"]["tone"])
    forbidden = "\n".join(f"- {t}" for t in persona["personality"]["forbidden"])
    emotions = ", ".join(persona["emotions"].keys())
    variation_block = build_variation_prompt(variation)

    dm = variation.get("dev_mode", "코칭")
    bd = _DEV_MODE_BEAT_DESC.get(dm, _DEV_MODE_BEAT_DESC["코칭"])

    return f"""당신은 와이파이 의인화 캐릭터 팡이의 전담 대본 작가입니다.

[팡이 기본 톤 규칙]
{tone_rules}

[절대 금지]
{forbidden}

[사용 가능한 감정] {emotions}

[에피소드 포맷 — 총 30~40초 이내, 6-beat]
beat 1 "후킹"    (3~5초):  시청자가 멈추게 만드는 도발적 본심 선언 한 줄
beat 2 "본심수신" (2~3초):  팡이가 본심 주파수 수신 — 안테나 번쩍 멘트
beat 3 "전개1"  (4~8초):  {bd[0]}
beat 4 "전개2"  (4~8초):  {bd[1]}
beat 5 "전개3"  (4~8초):  {bd[2]}
beat 6 "마무리"  (3~5초):  공범 윙크 + 다음 본심 투표 CTA
⚠️ 6개 beat 합산 TTS 기준 40초를 초과하지 말 것.
{variation_block}

⚠️ 전개1·2·3은 각각 독립된 짧은 문장. 이어서 읽는 연속 대사 금지 — 컷이 따로 나뉘므로.
⚠️ 한 대사에 비유·이미지는 1개만. 소리 내어 읽었을 때 한 번에 꽂혀야 함. 비유 2개 이상 겹치면 시청자가 못 따라감.
⚠️ 전개 각 줄은 구체적인 행동·꼼수·유형·순간 1개를 담을 것. 추상적 묘사나 감상으로 채우지 말 것.
각 beat의 "emphasis"는 그 대사에서 화면에 크게 강조할 핵심 단어 1개입니다.
반드시 해당 dialogue 안에 실제로 등장하는 짧은 단어/구(2~6자)를 고르세요.

반드시 아래 JSON 형식으로만 응답하세요 (beat는 정확히 6개):
{{
  "episode_no": <int>,
  "category": "<카테고리>",
  "topic": "<주제>",
  "beats": [
    {{"beat": "후킹",    "emotion": "<감정>", "dialogue": "<대사>", "emphasis": "<핵심 단어>", "duration_sec": 4, "video_prompt": "<Kling 영상 프롬프트 (영문)>"}},
    {{"beat": "본심수신","emotion": "<감정>", "dialogue": "<대사>", "emphasis": "<핵심 단어>", "duration_sec": 3, "video_prompt": "<Kling 영상 프롬프트 (영문)>"}},
    {{"beat": "전개1",   "emotion": "<감정>", "dialogue": "<대사>", "emphasis": "<핵심 단어>", "duration_sec": 6, "video_prompt": "<Kling 영상 프롬프트 (영문)>"}},
    {{"beat": "전개2",   "emotion": "<감정>", "dialogue": "<대사>", "emphasis": "<핵심 단어>", "duration_sec": 6, "video_prompt": "<Kling 영상 프롬프트 (영문)>"}},
    {{"beat": "전개3",   "emotion": "<감정>", "dialogue": "<대사>", "emphasis": "<핵심 단어>", "duration_sec": 6, "video_prompt": "<Kling 영상 프롬프트 (영문)>"}},
    {{"beat": "마무리",  "emotion": "{OUTRO_EMOTION}", "dialogue": "<대사>", "emphasis": "<핵심 단어>", "duration_sec": 5, "video_prompt": "<Kling 영상 프롬프트 (영문)>"}}
  ],
  "vote_options": ["<다음 주제 후보 A>", "<다음 주제 후보 B>"]
}}

[video_prompt 작성 규칙]
- 반드시 영문으로 작성
- 해당 beat의 대사·주제와 일치하는 배경·소품·분위기를 구체적으로 묘사
- 캐릭터 외형 묘사는 제외 (캐릭터는 레퍼런스 이미지로 고정됨)
- 예시: "Pokemon card packs scattered on table, glowing holographic rare card held up, dramatic backlight, colorful sparkles, vibrant 3D cartoon scene"
meme_ref는 감정 전환이 있는 beat에 선택적으로 추가 가능: {{"beat": "...", ..., "meme_ref": "<포즈·상황 설명>"}}"""


def _build_user_prompt(topic: str, category: str, episode_no: int, category_cfg: dict) -> str:
    extra_tone = ""
    if category_cfg.get("tone_additions"):
        extras = "\n".join(f"- {t}" for t in category_cfg["tone_additions"])
        extra_tone = f"\n[{category_cfg.get('category', category)} 카테고리 특화 톤]\n{extras}\n"

    extra_forbidden = ""
    if category_cfg.get("forbidden_additions"):
        fb = "\n".join(f"- {t}" for t in category_cfg["forbidden_additions"])
        extra_forbidden = f"\n[추가 금지 사항]\n{fb}\n"

    hook_examples = ""
    if category_cfg.get("example_hooks"):
        examples = "\n".join(f'  · "{h}"' for h in category_cfg["example_hooks"])
        hook_examples = f"\n[후킹 예시 (이 스타일로)]\n{examples}\n"

    return (
        f"카테고리: {category}\n"
        f"주제: {topic}\n"
        f"에피소드 번호: {episode_no}\n"
        f"{extra_tone}{extra_forbidden}{hook_examples}\n"
        "위 주제로 팡이 에피소드 대본을 JSON으로 작성해줘."
    )


def generate_pangi_script(topic: str, category: str = "직장", episode_no: int = 1,
                          extra_instruction: str = "") -> dict:
    persona = _load_persona()
    category_cfg = _load_category(category)
    allowed_modes = category_cfg.get("allowed_modes")
    variation = pick_variation(allowed_modes)
    system_prompt = _build_system_prompt(persona, variation)
    user_prompt   = _build_user_prompt(topic, category, episode_no, category_cfg)
    if extra_instruction:
        user_prompt += f"\n\n[추가 요청] {extra_instruction}"

    response = client.chat.completions.create(
        model="gpt-5.5",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    script = json.loads(response.choices[0].message.content)

    # 변주 이력 기록 — beat 1 실제 사용 감정 + dev_mode
    hook_emotion = script.get("beats", [{}])[0].get("emotion", variation["hook_emotion"])
    record_episode(episode_no, variation["hook_type"], variation["tone"], hook_emotion, variation["dev_mode"])

    # 하위 파이프라인(generate_clips 등)에서 참조 가능하도록 dev_mode 저장
    script["dev_mode"] = variation["dev_mode"]

    return script


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
