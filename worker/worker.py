from rq import Worker, Queue
from redis import Redis

redis_conn = Redis.from_url("redis://redis:6379/0")

if __name__ == "__main__":
    queues = [Queue("render_queue", connection=redis_conn),
              Queue("upload_queue", connection=redis_conn)]
    w = Worker(queues, connection=redis_conn)
    w.work()
