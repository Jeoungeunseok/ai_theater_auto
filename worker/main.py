import os
from redis import Redis
from rq import Worker, Queue

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
conn = Redis.from_url(redis_url)

if __name__ == "__main__":
    queues = [Queue("render_queue", connection=conn)]
    worker = Worker(queues, connection=conn)
    worker.work()
