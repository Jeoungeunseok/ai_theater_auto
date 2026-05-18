import os
import requests
from dotenv import load_dotenv

load_dotenv()

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

def fetch_pexels_image(query, output_path):
    """
    Pexels API를 사용하여 키워드에 맞는 이미지를 검색하고 저장합니다.
    """
    if not PEXELS_API_KEY:
        print("PEXELS_API_KEY not found in .env")
        return False
        
    url = f"https://api.pexels.com/v1/search?query={query}&per_page=1&orientation=portrait"
    headers = {"Authorization": PEXELS_API_KEY}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if data['photos']:
            img_url = data['photos'][0]['src']['large2x']
            img_data = requests.get(img_url).content
            with open(output_path, 'wb') as f:
                f.write(img_data)
            print(f"Downloaded asset for '{query}': {output_path}")
            return True
        else:
            print(f"No assets found for '{query}'")
            return False
    except Exception as e:
        print(f"Error fetching asset: {e}")
        return False

if __name__ == "__main__":
    # 테스트 실행
    os.makedirs("storage/bg_pool", exist_ok=True)
    fetch_pexels_image("traditional korean house", "storage/bg_pool/test.jpg")
