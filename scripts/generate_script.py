import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_short_script(topic):
    prompt = f"""
    주제: {topic}
    위 주제로 유튜브 쇼츠(60초 이내) 대본을 작성해줘.
    형식은 JSON으로 반환하고, 각 장면(scene)별로 내레이션(narration)과 자막(caption)을 포함해야 해.
    한국어 화자로 자연스럽고 흥미진진하게 작성해줘.
    
    예시 형식:
    {{
      "title": "흥부전의 비밀",
      "scenes": [
        {{
          "narration": "옛날 옛적, 마음씨 착한 흥부가 살았어요.",
          "caption": "마음씨 착한 흥부"
        }},
        ...
      ]
    }}
    """
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={ "type": "json_object" }
    )
    
    return json.loads(response.choices[0].message.content)

if __name__ == "__main__":
    script = generate_short_script("흥부전 Ep.01 - 제비가 가져온 보물")
    os.makedirs("tmp/aitheater", exist_ok=True)
    with open("tmp/aitheater/script_v1.json", "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)
    print("Script generated at tmp/aitheater/script_v1.json")
