import os
import json
import yaml
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def generate_short_script(topic, series_name="folktale"):
    """
    시리즈별 템플릿을 로드하여 대본을 생성합니다.
    """
    template_path = os.path.join(_BASE_DIR, "prompts", f"{series_name}.yaml")
    if not os.path.exists(template_path):
        template_path = os.path.join(_BASE_DIR, "prompts", "folktale.yaml")

    with open(template_path, 'r', encoding='utf-8') as f:
        template = yaml.safe_load(f)

    system_prompt = template.get("system_prompt", "당신은 유능한 쇼츠 대본 작가입니다.")
    user_prompt = template.get("script_format", "").replace("{topic}", topic)
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={ "type": "json_object" }
    )
    
    return json.loads(response.choices[0].message.content)

if __name__ == "__main__":
    script = generate_short_script("흥부전 Ep.01 - 제비가 가져온 보물")
    os.makedirs("tmp/aitheater", exist_ok=True)
    with open("tmp/aitheater/script_v1.json", "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)
    print("Script generated at tmp/aitheater/script_v1.json")
