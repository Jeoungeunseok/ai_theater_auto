import os
import time
import asyncio
import json
from scripts.generate_script import generate_short_script
from scripts.generate_voice import generate_voice_over
from scripts.fetch_assets import fetch_pexels_image
from scripts.render_short import render_full_short

def create_video_task(job_id: str, topic: str):
    """
    RQ 워커가 실행할 실제 영상 제작 태스크입니다.
    """
    tmp_dir = f"tmp/aitheater/{job_id}"
    os.makedirs(tmp_dir, exist_ok=True)
    
    try:
        # 1. 대본 생성
        print(f"[{job_id}] Step 1: Generating Script")
        script = generate_short_script(topic)
        script_path = os.path.join(tmp_dir, "script.json")
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)
            
        # 2. 음성 생성 (비동기 함수를 동기적으로 실행)
        print(f"[{job_id}] Step 2: Generating Voice")
        voice_dir = os.path.join(tmp_dir, "voice")
        asyncio.run(generate_voice_over(script_path, voice_dir))
        
        # 3. 배경 이미지 수집
        print(f"[{job_id}] Step 3: Fetching Background")
        bg_path = os.path.join(tmp_dir, "background.jpg")
        fetch_pexels_image("cinematic landscape", bg_path)
        
        # 4. 영상 렌더링
        print(f"[{job_id}] Step 4: Rendering Video")
        output_video = os.path.join(tmp_dir, "final.mp4")
        render_full_short(script_path, voice_dir, bg_path, output_video)
        
        print(f"[{job_id}] Task Completed Successfully: {output_video}")
        return {"status": "COMPLETED", "video_path": output_video}
        
    except Exception as e:
        print(f"[{job_id}] Task Failed: {str(e)}")
        return {"status": "FAILED", "error": str(e)}
