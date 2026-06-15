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

# 전개 모드별 beat 2·3(전개1·2) 설명 — 시스템 프롬프트 beat 포맷 섹션에 삽입
_DEV_MODE_BEAT_DESC = {
    "코칭": [
        "꼼수·해법 첫 번째 — 팡이 공범 어조로 임팩트 있게 하나만. 독립 완결 문장.",
        "꼼수·해법 두 번째 — 반전 또는 핵심 하이라이트로 마무리. 완결.",
    ],
    "유형": [
        "1번째 유형 지목 — '이런 사람/상황 있잖아' 공범 어조. 임팩트 있게.",
        "2번째 유형 — 반전·웃음 포인트로 마무리. 완결.",
    ],
    "상상현실": [
        "망상·기대 — 설렘·과장으로 시작. 독립 완결 문장.",
        "현실 충격 + 합리화 — 반전·허당 구조에 팡이가 공범으로 편들며 마무리. 완결.",
    ],
    "공감폭발": [
        "'이럴 때 이러지' 첫 번째 순간 — 팡이가 '나도 그래' 편들며 독립 완결.",
        "두 번째 공감 순간 — 반전 또는 핵심 공감으로 마무리. 완결.",
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

[에피소드 포맷 — 총 15~22초 이내, 4-beat]
beat 1 "후킹"   (3~5초):  시청자가 멈추게 만드는 도발적 본심 선언 한 줄
beat 2 "전개1"  (4~7초):  {bd[0]}
beat 3 "전개2"  (4~7초):  {bd[1]}
beat 4 "마무리" (3~5초):  공범 윙크 + 다음 본심 투표 CTA
⚠️ 4개 beat 합산 TTS 기준 22초를 초과하지 말 것. 짧고 임팩트 있게.
{variation_block}

⚠️ 전개1·2·3은 각각 독립된 짧은 문장. 이어서 읽는 연속 대사 금지 — 컷이 따로 나뉘므로.
⚠️ 한 대사에 비유·이미지는 1개만. 소리 내어 읽었을 때 한 번에 꽂혀야 함. 비유 2개 이상 겹치면 시청자가 못 따라감.
⚠️ 전개 각 줄은 구체적인 행동·꼼수·유형·순간 1개를 담을 것. 추상적 묘사나 감상으로 채우지 말 것.
각 beat의 "emphasis"는 그 대사에서 화면에 크게 강조할 핵심 단어 1개입니다.
반드시 해당 dialogue 안에 실제로 등장하는 짧은 단어/구(2~6자)를 고르세요.

[대사 품질 기준 — 반드시 지킬 것]

후킹 감정:
❌ 뿌듯함·평온·멍함 → 도발력 없음, 시청자가 안 멈춤
✅ 충격·심술·신남·자신감·설렘 → 눈길을 잡는 감정

후킹 대사:
❌ "심장이 왕좌에 앉아" → 의미불명, 추상적, 한 번에 안 꽂힘
✅ "카드깡 한 번 잘못하면 지갑이 먼저 울어" → 상황 명확, 구어체 직구, 비유 1개

전개 비유 규칙:
❌ "기대치가 에베레스트면 손이 떨려" → 비유 2개 겹침 (에베레스트 + 손 떨림)
✅ "뜯기 전엔 목표를 손맛으로만 잡아" → 구체적 행동 1개, 군더더기 없음

전개 추상 금지:
❌ "뇌가 불꽃놀이 한다" → 장면이 안 그려짐, 감상적
✅ "마지막 장 넘기기 직전 1초, 거기서 멈춰봐" → 행동·순간 명확, 화면이 그려짐

반드시 아래 JSON 형식으로만 응답하세요 (beat는 정확히 4개):
{{
  "episode_no": <int>,
  "category": "<카테고리>",
  "topic": "<주제>",
  "scene_setting": "<에피소드 전체 배경 묘사 (영문, 1~2문장) — 모든 beat에서 공유되는 공간·분위기>",
  "beats": [
    {{"beat": "후킹",   "emotion": "<감정>", "dialogue": "<대사>", "emphasis": "<핵심 단어>", "duration_sec": 4, "video_prompt": "<beat별 동작·반응 묘사 (영문) — scene_setting 제외>", "action_hold_sec": 0.15}},
    {{"beat": "전개1",  "emotion": "<감정>", "dialogue": "<대사>", "emphasis": "<핵심 단어>", "duration_sec": 6, "video_prompt": "<beat별 동작·반응 묘사 (영문) — scene_setting 제외>", "action_hold_sec": 0.15}},
    {{"beat": "전개2",  "emotion": "<감정>", "dialogue": "<대사>", "emphasis": "<핵심 단어>", "duration_sec": 6, "video_prompt": "<beat별 동작·반응 묘사 (영문) — scene_setting 제외>", "action_hold_sec": 0.15}},
    {{"beat": "마무리", "emotion": "{OUTRO_EMOTION}", "dialogue": "<대사>", "emphasis": "<핵심 단어>", "duration_sec": 5, "video_prompt": "<beat별 동작·반응 묘사 (영문) — scene_setting 제외>", "action_hold_sec": 0.15}}
  ],
  "vote_options": ["<다음 주제 후보 A>", "<다음 주제 후보 B>"]
}}

[action_hold_sec 작성 규칙]
- 음성이 끝난 뒤 그 컷을 몇 초 더 유지할지 (시각적 동작 완성용)
- 기본값 0.15 (음성 끝나면 바로 다음 컷)
- 단, video_prompt에 "끝까지 진행되어야 의미가 사는 동작"이 있으면 0.6~1.2 사이로 키울 것
  예) 얼굴이 돌처럼 굳는다, 천천히 무너진다, 폭발한다, 안테나가 점점 커진다 등
- 동작이 없고 말만 하는 컷이면 0.15 유지

[scene_setting 작성 규칙]
- 에피소드 주제와 딱 맞는 배경 공간을 영문으로 구체적으로 묘사
- 4개 beat 전체에서 공유되는 고정 배경 — 바뀌지 않음
- 예시(카드깡): "Convenience store card display wall, bright fluorescent lighting, colorful Pokemon card packs neatly arranged on shelves, 3D cartoon style"

[video_prompt 작성 규칙]
- scene_setting은 이미 자동으로 앞에 붙으므로 beat 고유 동작·반응만 영문으로 작성
- 캐릭터 외형 묘사 제외 (캐릭터는 레퍼런스 이미지로 고정됨)
- ⭐ 반드시 카메라 무빙을 한 개 끝에 명시 — 컷이 밋밋하지 않고 다이내믹해짐
  · 후킹: "slow zoom in" (긴장감 끌어올림)
  · 전개: "slow push in" / "camera pans left" / "slight dolly in" 중 택1
  · 마무리: "slow zoom out" (정리·여운)
- 예시: "character pointing dramatically at card pack, eyes wide with anticipation, slow zoom in"
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
