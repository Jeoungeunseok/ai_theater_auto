import os
import base64
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
IMAGE_QUALITY = os.getenv("IMAGE_QUALITY", "medium")

def generate_scene_image(prompt, output_path, style="digital art, high quality, cinematic lighting", reference_image_path=None):
    """
    gpt-image-2를 사용하여 특정 장면의 이미지를 생성합니다.
    reference_image_path가 있으면 캐릭터 일관성 유지에 활용됩니다.
    """
    full_prompt = f"{prompt}. Style: {style}."

    try:
        if reference_image_path and os.path.exists(reference_image_path):
            with open(reference_image_path, "rb") as img_file:
                response = client.images.edit(
                    model="gpt-image-2",
                    image=img_file,
                    prompt=full_prompt,
                    size="1024x1536",
                    response_format="b64_json",
                    n=1
                )
        else:
            response = client.images.generate(
                model="gpt-image-2",
                prompt=full_prompt,
                size="1024x1536",
                quality=IMAGE_QUALITY,
                response_format="b64_json",
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


def generate_images_for_script(script_data, output_dir, style="Korean folk tale illustration style, 2D, vibrant colors", reference_image_path=None):
    """
    대본 전체의 각 장면에 맞는 이미지를 생성합니다.
    """
    os.makedirs(output_dir, exist_ok=True)

    for i, scene in enumerate(script_data["scenes"]):
        image_path = os.path.join(output_dir, f"scene_{i:02d}.png")
        prompt = scene["narration"]
        print(f"Generating image for Scene {i}...")
        success = generate_scene_image(prompt, image_path, style=style, reference_image_path=reference_image_path)
        if not success:
            raise RuntimeError(f"Scene {i} 이미지 생성 실패: {prompt[:50]}")
