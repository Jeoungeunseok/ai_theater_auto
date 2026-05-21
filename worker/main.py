import os
from redis import Redis
from rq import Worker, Queue, Connection

# 환경변수에서 큐 목록 가져오기 (기본값: render_queue, upload_queue)
QUEUES = os.getenv("QUEUES", "render_queue,upload_queue").split(",")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

conn = Redis.from_url(REDIS_URL)

if __name__ == '__main__':
    with Connection(conn):
        worker = Worker(list(map(Queue, QUEUES)))
        worker.work()
