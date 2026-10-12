# Railway deployment preparation

This project is prepared for Railway as five services: **API**, **Telegram bot**, **recording worker**, **PostgreSQL**, and **Redis**. Railway maps Compose services into Railway services rather than running `docker-compose.yml` directly. Follow these steps after Railway account access is ready.

## Before creating services

- Choose a single Railway project and region.
- Confirm a billing plan before adding persistent services. Railway Hobby is currently $5/month and includes the first $5 of resource usage; actual compute, database, volume, and egress usage can raise the bill.
- For the worker, start with a persistent volume mounted at `/data/recordings`. The Hobby volume default is 5 GB; resize it based on how many recordings you expect to retain. Worker must stay at one replica while it owns a mounted volume.
- The Docker entrypoint initializes the mount directory and then drops to an unprivileged `botuser`. The API uses `${PORT:-8000}` so Railway can route a generated public domain to it.

## Services to create

### 1. Managed PostgreSQL

Add a Railway PostgreSQL database. Set `DATABASE_URL` for API, bot, and worker to the PostgreSQL service's private `DATABASE_URL` reference variable. The app normalizes generic `postgres://` / `postgresql://` URLs to the installed psycopg v3 driver.

### 2. Managed Redis

Add a Railway Redis database. Set `REDIS_URL` for API, bot, and worker to the Redis service's private `REDIS_URL` reference variable.

### 3. API service

Connect `bossdenmarkcruz-dev/tiktok-live-recorder-bot` on branch `main`. Use the repository-root `Dockerfile`. Leave the Docker CMD as-is. Add variables:

- `DATABASE_URL` — reference to PostgreSQL
- `REDIS_URL` — reference to Redis
- `API_BEARER_TOKEN` — long random secret
- `ALLOWED_TELEGRAM_USER_IDS` — optional comma-separated allowed Telegram user IDs
- `RECORDINGS_DIR=/data/recordings`
- `MAX_UPLOAD_MB=49`
- `MAX_RECORDING_HOURS=12`
- `RETENTION_DAYS=14`

Generate a public domain for this service, map it to the container's port `8000`, and test `/healthz`. The API key is required on `/v1/jobs` and `/v1/jobs/*` when `API_BEARER_TOKEN` is set.

### 4. Telegram bot service

Connect the same repo and Dockerfile. Set the start command to:

```sh
python -m app.bot
```

Set `DATABASE_URL`, `REDIS_URL`, `ALLOWED_TELEGRAM_USER_IDS` (if used), and `TELEGRAM_BOT_TOKEN`. Set `RECORDINGS_DIR=/data/recordings` for consistent configuration. The token belongs in Railway's secret variable UI only; do not put it in GitHub or paste it into chat.

### 5. Recording worker service

Connect the same repo and Dockerfile. Set the start command to:

```sh
python -m app.worker_main
```

Set `DATABASE_URL`, `REDIS_URL`, `TELEGRAM_BOT_TOKEN`, `RECORDINGS_DIR=/data/recordings`, `MAX_UPLOAD_MB=49`, `MAX_RECORDING_HOURS=12`, and `RETENTION_DAYS=14`. Attach the persistent volume at `/data/recordings`. Keep a single worker replica to avoid concurrent mounts/recordings on one volume.

## Go-live order

1. Add the variables and volume, but do not deploy billable resources until the Railway plan and expected charge are confirmed.
2. Deploy Postgres and Redis, then API, bot, and worker.
3. Verify the API health check. Send `/start` to the bot and submit a test request only for a stream you own or are authorized to record.
4. Monitor Railway usage and volume capacity. The recorder has a 12-hour safety cap and retains completed files for 14 days when a new job starts; adjust settings to suit the actual volume size.
