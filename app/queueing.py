from redis import Redis
from rq import Queue
from app.config import settings


def redis_connection() -> Redis:
    return Redis.from_url(settings.redis_url, socket_connect_timeout=5, socket_timeout=5)


def enqueue_recording(job_id: str) -> str:
    queue = Queue("recordings", connection=redis_connection(), default_timeout=settings.max_recording_hours * 3600 + 1800)
    task = queue.enqueue(
        "app.worker.record_and_deliver",
        job_id,
        job_id=job_id,
        job_timeout=settings.max_recording_hours * 3600 + 1800,
        result_ttl=0,
        failure_ttl=86400,
    )
    return task.id
