import os
from db.database import SessionLocal
from db.models import Episode, Vote
from api.youtube import get_youtube_client
import re

def collect_comments_and_vote(episode_id: int):
    """
    YouTube 댓글을 수집하여 선택지별로 투표수를 집계합니다.
    """
    db = SessionLocal()
    try:
        episode = db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode or not episode.youtube_video_id:
            print(f"Episode {episode_id} or YouTube Video ID not found")
            return

        youtube = get_youtube_client()
        if not youtube:
            return

        # 1. 댓글 수집 (최상위 댓글만 간단히 수집)
        request = youtube.commentThreads().list(
            part="snippet",
            videoId=episode.youtube_video_id,
            maxResults=100
        )
        response = request.execute()

        # 2. 투표 집계 로직 (단순 키워드 매칭)
        # 예: 선택지가 "치료", "외면" 인 경우
        # 실제로는 대본 생성 시 선택지를 DB에 저장해두고 가져와야 함
        choices = ["치료", "외면"] 
        votes_count = {choice: 0 for choice in choices}

        for item in response.get('items', []):
            comment = item['snippet']['topLevelComment']['snippet']['textDisplay']
            for choice in choices:
                if choice in comment:
                    votes_count[choice] += 1

        # 3. DB 업데이트
        for choice, count in votes_count.items():
            vote = db.query(Vote).filter(
                Vote.episode_id == episode_id, 
                Vote.choice_key == choice
            ).first()
            
            if vote:
                vote.count = count
            else:
                new_vote = Vote(
                    episode_id=episode_id,
                    choice_key=choice,
                    count=count
                )
                db.add(new_vote)
        
        db.commit()
        print(f"Votes updated for Episode {episode_id}: {votes_count}")

        # 4. Slack 보고
        from api.slack import client
        report_text = f"📊 *Ep.{episode.episode_no} 투표 결과 보고*\n"
        for choice, count in votes_count.items():
            report_text += f"- {choice}: {count}표\n"
        
        client.chat_postMessage(channel="#ai-theater-alerts", text=report_text)

    except Exception as e:
        print(f"Error collecting comments: {e}")
    finally:
        db.close()
