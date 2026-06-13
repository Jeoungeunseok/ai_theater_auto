import os
import base64
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_QUALITY = os.getenv("BG_IMAGE_QUALITY", "medium")

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EYES_DIR = os.path.join(_BASE_DIR, "assets", "pang", "eyes")
_BODY_PATH = os.path.join(_BASE_DIR, os.getenv("PANGI_BODY", "assets/pang/base/body_front.png"))

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
    """배경 이미지 1장 생성. 캐릭터 없이 배경만."""
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


def _collect_refs(emotion: str, char_image_path: str = None) -> list:
    """캐릭터 레퍼런스 + 감정 눈 이미지 파일 핸들 목록 반환."""
    refs = []
    body = char_image_path or _BODY_PATH
    if os.path.exists(body):
        refs.append(open(body, "rb"))
    eye_path = os.path.join(_EYES_DIR, f"{emotion}.png")
    if os.path.exists(eye_path):
        refs.append(open(eye_path, "rb"))
    return refs


def generate_cut_images(beat: dict, beat_idx: int, output_dir: str,
                        n_candidates: int = 1,
                        char_image_path: str = None,
                        edit_prompt: str = "") -> list[str]:
    """beat 1개 → gpt-image-2 edit 모드로 장면 이미지 생성.

    캐릭터 레퍼런스(body) + 감정 눈 이미지(eyes)를 함께 전달해
    팡이의 외형과 표정을 일관되게 유지한다.
    edit_prompt 있으면 수정 지시로 사용.
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
            f"Match the eye expression shown in the reference eye image exactly. "
            f"Vertical 9:16 format. No text in image."
        )
    else:
        prompt = (
            f"Korean short-form video scene illustration. "
            f"Character: Pangi, a cute blue 3D cartoon Wi-Fi signal mascot with antenna ears and big round eyes. "
            f"Match the eye expression shown in the reference eye image exactly: {emotion_desc}. "
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
        print(f"    [이미지] beat_{beat_idx:02d} gpt-image-2 edit 생성 중... ({beat_name}/{emotion})")
        refs = []
        try:
            refs = _collect_refs(emotion, char_image_path)
            if refs:
                response = client.images.edit(
                    model="gpt-image-2",
                    image=refs if len(refs) > 1 else refs[0],
                    prompt=prompt,
                    n=1,
                    size="1024x1536",
                    quality="medium",
                )
            else:
                # 레퍼런스 이미지 없으면 generate 폴백
                print(f"    [WARN] beat_{beat_idx:02d} 레퍼런스 없음 — generate 폴백")
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
        finally:
            for ref in refs:
                ref.close()

    return paths


if __name__ == "__main__":
    generate_background(
        topic="상사 몰래 쉬는 법",
        category="직장",
        output_path="assets/bg/ep01_workplace.webp",
    )
