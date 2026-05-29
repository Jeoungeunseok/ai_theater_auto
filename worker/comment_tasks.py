import json
from db.database import SessionLocal
from db.models import Episode, Vote
from api.youtube import get_youtube_client
from worker.slack_notifier import send_vote_report


def collect_comments_and_vote(episode_id: int):
    """YouTube 댓글 수집 → 투표 집계 → DB 저장 → Slack 리포트."""
    db = SessionLocal()
    try:
        episode = db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode or not episode.youtube_video_id:
            print(f"Episode {episode_id} 또는 YouTube ID 없음")
            return

        if not episode.vote_options:
            print(f"Episode {episode_id} vote_options 없음")
            return
        vote_options = json.loads(episode.vote_options)

        youtube = get_youtube_client()
        if not youtube:
            return

        # 댓글 전체 수집 (페이지네이션)
        all_items = []
        next_page_token = None
        while True:
            resp = youtube.commentThreads().list(
                part="snippet",
                videoId=episode.youtube_video_id,
                maxResults=100,
                pageToken=next_page_token,
            ).execute()
            all_items.extend(resp.get("items", []))
            next_page_token = resp.get("nextPageToken")
            if not next_page_token:
                break

        # 투표 집계 (키워드 매칭)
        votes_count = {opt: 0 for opt in vote_options}
        for item in all_items:
            comment = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
            for opt in vote_options:
                if opt in comment:
                    votes_count[opt] += 1

        # DB upsert
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

        # 최다 득표 → 다음 주제 시드
        next_topic = max(votes_count, key=votes_count.get) if votes_count else ""
        send_vote_report(episode.episode_no, votes_count, next_topic=next_topic)
        print(f"Ep.{episode.episode_no} 투표 집계 완료: {votes_count}")

    except Exception as e:
        print(f"댓글 수집 오류: {e}")
    finally:
        db.close()
