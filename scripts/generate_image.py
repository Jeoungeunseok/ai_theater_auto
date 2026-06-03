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
                        n_candidates: int = 2,
                        char_image_path: str = None) -> list[str]:
    """beat 1개 → fal.ai 정지 이미지 n_candidates장 생성.

    I2V 전 이미지 게이트용. 레퍼런스(body_front.png) + 감정 + 장면 프롬프트로
    팡이 캐릭터 일관성을 유지하면서 컷별 표정/배경 이미지를 생성한다.

    Returns: 생성된 이미지 파일 경로 목록. FAL_KEY 미설정 시 빈 리스트 반환.
    """
    try:
        import fal_client
    except ImportError:
        raise ImportError("fal-client 필요: pip install fal-client")

    if not os.getenv("FAL_KEY"):
        print(f"[WARN] FAL_KEY 미설정 — beat_{beat_idx} 이미지 생성 건너뜀")
        return []

    char_path = char_image_path or os.getenv("PANGI_BODY", "assets/pang/base/body_front.png")
    beat_name = beat.get("beat", "꿀팁3단")
    emotion = beat.get("emotion", "평온")
    emotion_desc = _EMOTION_EN.get(emotion, "neutral expression")
    scene_desc = _BEAT_SCENE.get(beat_name, "colorful simple background")

    prompt = (
        f"팡이(Pangi), an anthropomorphic Wi-Fi signal mascot character. "
        f"Keep the exact same character design as the reference image — do NOT redesign the character. "
        f"Expression: {emotion_desc}. "
        f"Background scene: {scene_desc}. "
        f"3D cartoon animation style, vertical 9:16 format, character centered in frame."
    )
    negative_prompt = "different character, redesign, human, realistic, text, watermark, blurry"

    cut_dir = os.path.join(output_dir, f"beat_{beat_idx:02d}")
    os.makedirs(cut_dir, exist_ok=True)

    print(f"    [이미지] beat_{beat_idx:02d} 레퍼런스 업로드...")
    image_url = fal_client.upload_file(char_path)

    # elements 방식 = 캐릭터 잠금 / image_url 방식 = 느슨한 참고
    # PANGI_IMAGE_USE_ELEMENTS=true + 올바른 elements 파라미터명으로 캐릭터 일관성 확보
    if _IMAGE_USE_ELEMENTS:
        ref_arg = {
            _IMAGE_ELEMENTS_PARAM: [{"image_url": image_url, "weight": 1.0}]
        }
        print(f"    [이미지] elements 방식 ({_IMAGE_ELEMENTS_PARAM}) — 캐릭터 잠금 모드")
    else:
        ref_arg = {_IMAGE_REF_PARAM: image_url}
        print(f"    [이미지] 단일 레퍼런스 방식 ({_IMAGE_REF_PARAM}) — elements 활성화 권장")

    paths = []
    for i in range(n_candidates):
        out_path = os.path.join(cut_dir, f"candidate_{i:02d}.webp")
        print(f"    [이미지] beat_{beat_idx:02d} candidate {i+1}/{n_candidates} 생성 중...")
        try:
            result = fal_client.run(
                _IMAGE_MODEL,
                arguments={
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    **ref_arg,
                    "aspect_ratio": "9:16",
                    "num_images": 1,
                },
            )
            img_url = result["images"][0]["url"]
            resp = requests.get(img_url, timeout=60)
            resp.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(resp.content)
            paths.append(out_path)
            print(f"    [이미지] beat_{beat_idx:02d} candidate {i} 저장: {out_path}")
        except Exception as e:
            print(f"    [WARN] beat_{beat_idx:02d} candidate {i} 생성 실패: {e}")

    return paths


if __name__ == "__main__":
    generate_background(
        topic="상사 몰래 쉬는 법",
        category="직장",
        output_path="assets/bg/ep01_workplace.webp",
    )
