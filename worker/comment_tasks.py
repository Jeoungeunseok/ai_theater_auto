"""
발행 48시간 후 YouTube 댓글 수집 → 투표 집계 → 다음 주제 자동 결정
"""
import json
import os
from openai import OpenAI
from dotenv import load_dotenv
from db.database import SessionLocal
from db.models import Episode, Vote
from api.youtube import get_youtube_client
from worker.slack_notifier import send_vote_report

load_dotenv()
_openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def collect_comments_and_vote(episode_id: int):
    """YouTube 댓글 수집 → LLM 보조 투표 집계 → DB 저장 → Slack 리포트."""
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
        all_comments = _fetch_all_comments(youtube, episode.youtube_video_id)
        print(f"  수집된 댓글: {len(all_comments)}개")

        # 투표 집계 — 정규식 선매칭, 미분류는 LLM 보조
        votes_count = _count_votes(all_comments, vote_options)

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

        # 최다 득표 → 다음 주제 결정 후 큐 투입
        winner = max(votes_count, key=votes_count.get) if votes_count else ""
        send_vote_report(episode.episode_no, votes_count, next_topic=winner)
        print(f"Ep.{episode.episode_no} 투표 집계 완료: {votes_count}")

        if winner:
            _schedule_next_episode(winner, episode.category, episode.episode_no + 1)

    except Exception as e:
        print(f"댓글 수집 오류: {e}")
    finally:
        db.close()


def _fetch_all_comments(youtube, video_id: str) -> list[str]:
    all_items = []
    next_page_token = None
    while True:
        resp = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=100,
            pageToken=next_page_token,
        ).execute()
        all_items.extend(resp.get("items", []))
        next_page_token = resp.get("nextPageToken")
        if not next_page_token:
            break
    return [
        item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
        for item in all_items
    ]


def _count_votes(comments: list[str], vote_options: list[str]) -> dict[str, int]:
    """정규식으로 1차 매칭, 미분류 댓글은 GPT로 2차 분류."""
    counts = {opt: 0 for opt in vote_options}
    unclassified = []

    for comment in comments:
        matched = False
        for opt in vote_options:
            if opt in comment:
                counts[opt] += 1
                matched = True
                break
        if not matched and len(comment.strip()) > 1:
            unclassified.append(comment)

    # GPT 보조: 미분류 댓글 배치 분류 (최대 50개)
    if unclassified and vote_options:
        llm_counts = _llm_classify(unclassified[:50], vote_options)
        for opt, cnt in llm_counts.items():
            counts[opt] = counts.get(opt, 0) + cnt

    return counts


def _llm_classify(comments: list[str], vote_options: list[str]) -> dict[str, int]:
    """GPT로 댓글을 투표 옵션에 분류."""
    options_str = " / ".join(f'"{o}"' for o in vote_options)
    comments_str = "\n".join(f"- {c[:80]}" for c in comments)

    prompt = (
        f"다음 댓글들이 어느 주제에 투표하는지 분류해줘.\n"
        f"투표 옵션: {options_str}\n\n"
        f"댓글:\n{comments_str}\n\n"
        f"각 옵션의 득표수를 JSON으로: {{\"옵션명\": 득표수, ...}}"
    )
    try:
        resp = _openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"  [WARN] LLM 분류 실패: {e}")
        return {}


def _schedule_next_episode(winner_topic: str, category: str, next_ep_no: int):
    """투표 우승 주제로 다음 에피소드 자동 큐 투입."""
    try:
        from redis import Redis
        from rq import Queue
        redis_conn = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        q = Queue("render_queue", connection=redis_conn)
        import uuid
        job_id = str(uuid.uuid4())

        from db.database import SessionLocal as SL
        from db.models import Job, JobStatus
        db2 = SL()
        new_job = Job(
            id=job_id,
            topic=winner_topic,
            category=category,
            episode_no=next_ep_no,
            status=JobStatus.PENDING,
        )
        db2.add(new_job)
        db2.commit()
        db2.close()

        q.enqueue("worker.tasks.create_script_task", job_id, winner_topic, category, next_ep_no)
        print(f"  → 다음 화 Ep.{next_ep_no:02d} 자동 큐 투입: {winner_topic}")
    except Exception as e:
        print(f"  [WARN] 다음 화 큐 투입 실패: {e}")
