import os
import requests
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_scene_image(prompt, output_path, style="digital art, high quality, cinematic lighting"):
    """
    DALL-E 3를 사용하여 특정 장면의 이미지를 생성합니다.
    """
    full_prompt = f"{prompt}. Style: {style}."
    
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=full_prompt,
            size="1024x1792", # 쇼츠에 적합한 세로형 사이즈
            quality="standard",
            n=1
        )
        
        image_url = response.data[0].url
        img_data = requests.get(image_url).content
        with open(output_path, 'wb') as f:
            f.write(img_data)
        print(f"Successfully generated image: {output_path}")
        return True
    except Exception as e:
        print(f"Error generating image with DALL-E: {e}")
        return False

def generate_images_for_script(script_data, output_dir, style="Korean folk tale illustration style, 2D, vibrant colors"):
    """
    대본 전체의 각 장면에 맞는 이미지를 생성합니다.
    """
    os.makedirs(output_dir, exist_ok=True)

    for i, scene in enumerate(script_data["scenes"]):
        image_path = os.path.join(output_dir, f"scene_{i:02d}.png")
        prompt = scene["narration"]
        print(f"Generating image for Scene {i}...")
        success = generate_scene_image(prompt, image_path, style=style)
        if not success:
            raise RuntimeError(f"Scene {i} 이미지 생성 실패: {prompt[:50]}")
