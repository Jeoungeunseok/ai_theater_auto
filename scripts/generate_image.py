import os
import base64
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
IMAGE_QUALITY = os.getenv("IMAGE_QUALITY", "medium")

def generate_scene_image(prompt, output_path, style="digital art, high quality, cinematic lighting", reference_image_paths=None):
    """
    gpt-image-2를 사용하여 특정 장면의 이미지를 생성합니다.
    reference_image_paths: 컨셉아트, 표정묘사 등 레퍼런스 이미지 경로 리스트 (최대 16장)
    """
    full_prompt = f"{prompt}. Style: {style}."
    valid_paths = [p for p in (reference_image_paths or []) if p and os.path.exists(p)]

    try:
        if valid_paths:
            file_handles = [open(p, "rb") for p in valid_paths]
            try:
                response = client.images.edit(
                    model="gpt-image-2",
                    image=file_handles if len(file_handles) > 1 else file_handles[0],
                    prompt=full_prompt,
                    size="1024x1536",
                    n=1
                )
            finally:
                for f in file_handles:
                    f.close()
        else:
            response = client.images.generate(
                model="gpt-image-2",
                prompt=full_prompt,
                size="1024x1536",
                quality=IMAGE_QUALITY,
                n=1
            )

        image_data = base64.b64decode(response.data[0].b64_json)
        with open(output_path, "wb") as f:
            f.write(image_data)
        print(f"Successfully generated image: {output_path}")
        return True
    except Exception as e:
        print(f"Error generating image with gpt-image-2: {e}")
        return False


def generate_images_for_script(script_data, output_dir, style="Korean folk tale illustration style, 2D, vibrant colors", reference_image_paths=None):
    """
    대본 전체의 각 장면에 맞는 이미지를 생성합니다.
    캐릭터 첫 등장 이미지를 이후 동일 캐릭터 장면의 레퍼런스로 자동 추가합니다.
    """
    os.makedirs(output_dir, exist_ok=True)

    # 캐릭터별 첫 등장 이미지 경로 추적
    character_first_image: dict = {}

    for i, scene in enumerate(script_data["scenes"]):
        image_path = os.path.join(output_dir, f"scene_{i:02d}.png")
        scene_desc = scene.get("scene_description") or scene.get("narration", "")
        emotion = scene.get("emotion", "")
        character = scene.get("character", "")
        prompt = f"{scene_desc} Character: {character}. Emotion: {emotion}." if emotion else scene_desc

        # 동일 캐릭터의 첫 등장 이미지가 있으면 레퍼런스에 추가
        char_refs = list(reference_image_paths or [])
        if character in character_first_image:
            char_refs.append(character_first_image[character])

        print(f"Generating image for Scene {i} [{character} / {emotion}]...")
        success = generate_scene_image(prompt, image_path, style=style, reference_image_paths=char_refs)
        if not success:
            raise RuntimeError(f"Scene {i} 이미지 생성 실패: {prompt[:50]}")

        # 이 캐릭터의 첫 등장 이미지로 등록
        if character and character not in character_first_image:
            character_first_image[character] = image_path
