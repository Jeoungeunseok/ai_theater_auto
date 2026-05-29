import os
import base64
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_QUALITY = os.getenv("BG_IMAGE_QUALITY", "medium")

_CATEGORY_STYLE = {
    "직장": "modern office interior, clean minimal illustration, Korean webtoon style",
    "욕망": "colorful temptation scene, vibrant pop art style, Korean webtoon style",
    "부부": "cozy home interior, warm tones, Korean webtoon style",
    "일상": "everyday Korean city street or home, soft illustration style",
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


if __name__ == "__main__":
    generate_background(
        topic="상사 몰래 쉬는 법",
        category="직장",
        output_path="assets/bg/ep01_workplace.webp",
    )
