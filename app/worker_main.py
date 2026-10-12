from redis import Redis
from rq import Queue, Worker
from app.config import settings
from app.db import init_db


def main() -> None:
    init_db()
    connection = Redis.from_url(settings.redis_url)
    queues = [Queue("recordings", connection=connection)]
    Worker(queues, connection=connection).work(with_scheduler=False)


if __name__ == "__main__":
    main()
