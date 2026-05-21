import os
import shutil
import time

def cleanup_old_files(target_dir="tmp/aitheater", age_hours=24):
    """
    지정된 시간이 지난 임시 파일 및 폴더를 삭제합니다.
    """
    if not os.path.exists(target_dir):
        print(f"Directory {target_dir} does not exist. Skipping cleanup.")
        return

    now = time.time()
    cutoff = now - (age_hours * 3600)
    
    removed_count = 0
    print(f"Starting cleanup in {target_dir} (older than {age_hours} hours)...")

    for item in os.listdir(target_dir):
        item_path = os.path.join(target_dir, item)
        # 파일 또는 폴더의 수정 시간을 확인
        item_time = os.path.getmtime(item_path)
        
        if item_time < cutoff:
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)
                print(f"  Removed: {item_path}")
                removed_count += 1
            except Exception as e:
                print(f"  Failed to remove {item_path}: {e}")

    print(f"Cleanup finished. Total items removed: {removed_count}")

if __name__ == "__main__":
    # 기본적으로 24시간이 지난 파일 삭제
    cleanup_old_files()
