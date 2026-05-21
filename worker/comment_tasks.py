import json
from db.database import SessionLocal
from db.models import Episode, Vote
from api.youtube import get_youtube_client
from api.slack import client as slack_client

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

        if not episode.choices:
            print(f"Episode {episode_id} has no choices defined")
            return
        choices = json.loads(episode.choices)

        youtube = get_youtube_client()
        if not youtube:
            return

        # 1. 댓글 전체 수집 (페이지네이션 처리)
        all_items = []
        next_page_token = None
        while True:
            request = youtube.commentThreads().list(
                part="snippet",
                videoId=episode.youtube_video_id,
                maxResults=100,
                pageToken=next_page_token,
            )
            response = request.execute()
            all_items.extend(response.get("items", []))
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        # 2. 투표 집계 (키워드 매칭)
        votes_count = {choice: 0 for choice in choices}
        for item in all_items:
            comment = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
            for choice in choices:
                if choice in comment:
                    votes_count[choice] += 1

        # 3. DB 업데이트 (upsert)
        for choice, count in votes_count.items():
            vote = db.query(Vote).filter(
                Vote.episode_id == episode_id,
                Vote.choice_key == choice,
            ).first()

            if vote:
                vote.count = count
            else:
                db.add(Vote(episode_id=episode_id, choice_key=choice, count=count))

        db.commit()
        print(f"Votes updated for Episode {episode_id}: {votes_count}")

        # 4. Slack 보고
        report_text = f"*Ep.{episode.episode_no} 투표 결과 보고*\n"
        for choice, count in votes_count.items():
            report_text += f"- {choice}: {count}표\n"
        slack_client.chat_postMessage(channel="#ai-theater-alerts", text=report_text)

    except Exception as e:
        print(f"Error collecting comments: {e}")
    finally:
        db.close()
