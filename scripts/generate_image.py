import os
import base64
import requests
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_QUALITY = os.getenv("BG_IMAGE_QUALITY", "medium")

# fal.ai Kling 이미지 생성 모델 설정
#
# ⭐ 캐릭터 잠금의 핵심: "참고(image_url)" vs "잠금(elements)"
#
#   image_url 단일 레퍼런스 = 느슨한 참고 → 팡이 외형이 컷마다 흔들릴 수 있음
#   elements / 멀티 레퍼런스  = 캐릭터 고정 → 팡이 외형을 실제로 잠금
#
# fal.ai 대시보드에서 모델 파라미터 확인 후 .env에서 설정:
#   PANGI_IMAGE_MODEL     : elements 지원 모델 ID (예: "fal-ai/kling-image/v2-master")
#   PANGI_IMAGE_USE_ELEMENTS=true : elements 배열 방식 사용 (권장)
#   PANGI_IMAGE_ELEMENTS_PARAM    : elements 파라미터 이름 (fal.ai 대시보드 확인)
#                                   예: "elements" / "reference_images" / "subject_references"
#   PANGI_IMAGE_REF_PARAM         : 단일 이미지 파라미터 이름 (fallback, 기본 "image_url")
#
_IMAGE_MODEL = os.getenv("PANGI_IMAGE_MODEL", "fal-ai/kling-image/v2-master")
_IMAGE_USE_ELEMENTS = os.getenv("PANGI_IMAGE_USE_ELEMENTS", "false").lower() == "true"
_IMAGE_ELEMENTS_PARAM = os.getenv("PANGI_IMAGE_ELEMENTS_PARAM", "elements")
_IMAGE_REF_PARAM = os.getenv("PANGI_IMAGE_REF_PARAM", "image_url")

_CATEGORY_STYLE = {
    "직장": "modern office interior, clean minimal illustration, Korean webtoon style",
    "욕망": "colorful temptation scene, vibrant pop art style, Korean webtoon style",
    "부부": "cozy home interior, warm tones, Korean webtoon style",
    "일상": "everyday Korean city street or home, soft illustration style",
}

_EMOTION_EN = {
    "평온":   "calm and neutral expression",
    "기쁨":   "happy and joyful expression",
    "신남":   "excited and energetic expression",
    "설렘":   "thrilled and anticipating expression",
    "뿌듯함": "proud and satisfied expression",
    "자신감": "confident and assertive expression",
    "슬픔":   "sad and droopy expression",
    "분노":   "angry and frustrated expression",
    "무서움": "scared and nervous expression",
    "충격":   "shocked and surprised expression",
    "심술":   "mischievous and sly expression",
    "멍함":   "dazed and confused expression",
    "과부하": "overwhelmed and overloaded expression",
    "재부팅": "rebooting and resetting expression",
}

_BEAT_SCENE = {
    "후킹":    "dynamic foreground with dramatic lighting, slightly blurred background",
    "본심수신": "abstract signal wave background, vibrant glowing colors",
    "꿀팁3단": "clean minimal bright background, infographic-friendly",
    "마무리":  "warm cheerful background, positive and bright mood",
}


def generate_background(topic: str, category: str = "일상", output_path: str = "assets/bg/bg.webp") -> bool:
    """배경 이미지 1장 생성. 캐릭터 없이 배경만 — 팡이는 퍼펫으로 별도 합성."""
    style = _CATEGORY_STYLE.get(category, _CATEGORY_STYLE["일상"])
    prompt = (
        f"Background scene for a Korean short-form video about '{topic}'. "
        f"Style: {style}. "
        "No characters or people. Vertical 9:16 format. "
        "Slightly blurred or darkened at bottom for subtitle area."
    )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    try:
        response = client.images.generate(
            model="gpt-image-2",
            prompt=prompt,
            size="1024x1536",
            quality=_QUALITY,
            n=1,
        )
        image_data = base64.b64decode(response.data[0].b64_json)
        with open(output_path, "wb") as f:
            f.write(image_data)
        print(f"배경 이미지 생성 완료: {output_path}")
        return True
    except Exception as e:
        print(f"배경 이미지 생성 실패: {e}")
        return False


def generate_cut_images(beat: dict, beat_idx: int, output_dir: str,
                        n_candidates: int = 1,
                        char_image_path: str = None,
                        edit_prompt: str = "") -> list[str]:
    """beat 1개 → gpt-image-2로 장면 이미지 생성.

    주제·감정·대사를 기반으로 팡이가 등장하는 장면을 생성한다.
    edit_prompt 있으면 수정 지시로 사용.

    Returns: 생성된 이미지 파일 경로 목록.
    """
    beat_name = beat.get("beat", "전개")
    emotion = beat.get("emotion", "평온")
    dialogue = beat.get("dialogue", "")
    emphasis = beat.get("emphasis", "")
    emotion_desc = _EMOTION_EN.get(emotion, "neutral expression")
    scene_desc = _BEAT_SCENE.get(beat_name, "colorful simple background")

    if edit_prompt:
        prompt = (
            f"{edit_prompt}. "
            f"Character: Pangi, a cute blue 3D cartoon Wi-Fi signal mascot with antenna ears and big round eyes. "
            f"Vertical 9:16 format. No text in image."
        )
    else:
        prompt = (
            f"Korean short-form video scene illustration. "
            f"Character: Pangi, a cute blue 3D cartoon Wi-Fi signal mascot with antenna ears and big round eyes. "
            f"Expression: {emotion_desc}. "
            f"Scene concept: '{dialogue}' — visually show this moment. "
            f"Background: {scene_desc}. "
            f"Key visual emphasis: '{emphasis}'. "
            f"Style: bright vibrant 3D cartoon, vertical 9:16 format, character centered. "
            f"No text or letters in image."
        )

    cut_dir = os.path.join(output_dir, f"beat_{beat_idx:02d}")
    os.makedirs(cut_dir, exist_ok=True)

    paths = []
    for i in range(n_candidates):
        out_path = os.path.join(cut_dir, f"candidate_{i:02d}.png")
        print(f"    [이미지] beat_{beat_idx:02d} gpt-image-2 생성 중... ({beat_name}/{emotion})")
        try:
            response = client.images.generate(
                model="gpt-image-2",
                prompt=prompt,
                n=1,
                size="1024x1536",
                quality="medium",
            )
            img_bytes = base64.b64decode(response.data[0].b64_json)
            with open(out_path, "wb") as f:
                f.write(img_bytes)
            paths.append(out_path)
            print(f"    [이미지] beat_{beat_idx:02d} 저장 완료: {out_path}")
        except Exception as e:
            print(f"    [WARN] beat_{beat_idx:02d} candidate {i} 생성 실패: {e}")

    return paths


if __name__ == "__main__":
    generate_background(
        topic="상사 몰래 쉬는 법",
        category="직장",
        output_path="assets/bg/ep01_workplace.webp",
    )
