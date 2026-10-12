# TikTok LIVE Recorder Telegram Bot

A self-hostable Telegram bot that accepts `/download_replay <TikTok LIVE URL>`, verifies the page is an active TikTok LIVE, records the stream with `yt-dlp`/FFmpeg, and sends the resulting MP4 when recording ends. It includes a FastAPI backend, PostgreSQL job history, Redis/RQ workers, status commands, and Docker Compose deployment.

> **Important behavior:** this records the stream from the time the worker joins. It does not retrieve a creator's private/archived replay and cannot recover content from before the recording starts. If you submit after a LIVE has begun, the recording begins at the join point. TikTok availability, access controls, regional restrictions, and extractor changes can prevent recording. Use only for streams you own or are authorized to record, and comply with applicable laws and platform terms.

## Commands

- `/start` or `/help` — usage and limitations
- `/download_replay "https://www.tiktok.com/@creator/live"` — queue a recording check
- `/status <job_id>` — inspect state and elapsed recording time

Worker states: `queued` → `checking` → `recording` → `processing` → `sending` → `completed` (or `failed`). The end time is controlled by the broadcaster, so an exact finish ETA is not knowable. The bot reports this and automatically delivers the recording once the stream ends.

Only direct TikTok `/@handle/live` URLs are accepted; URL shorteners and other domains are rejected before they reach the downloader. A second identical active request from the same user/chat is deduplicated.

## Start with Docker Compose

1. In Telegram, open the official **@BotFather** account and send `/newbot`.
2. Follow its prompts for a display name and a unique username ending in `bot`. BotFather will reply with the bot's HTTP API token; treat that token like a password.
3. Copy the token into `TELEGRAM_BOT_TOKEN` in your private `.env` file or your hosting provider's secret/environment-variable settings. **Do not paste it into GitHub, commit it, or send it in chat.** If it is exposed, revoke it through BotFather and update the stored secret.
4. Copy `.env.example` to `.env`, then set `POSTGRES_PASSWORD` and a long random `API_BEARER_TOKEN`. Use an alphanumeric password (for example, generate one with `openssl rand -hex 24`) because Compose places it in a database URL. For private use, also set `ALLOWED_TELEGRAM_USER_IDS` to a comma-separated list of numeric Telegram user IDs. Keep `.env` private.
5. Start all services:

   ```bash
   docker compose up -d --build
   docker compose ps
   docker compose logs -f bot worker api
   ```

6. Check the API on the host: `curl http://127.0.0.1:8000/healthz`
7. Message the bot with `/start`.

Services are split so bot polling, HTTP API, and video recording can restart independently. Postgres, Redis, and recordings use persistent Docker volumes. The API is bound to `127.0.0.1` by default; put it behind a TLS reverse proxy if remote access is needed. Do not expose it publicly without a strong `API_BEARER_TOKEN` and an access-control policy.

## HTTP API

Base URL: `http://localhost:8000`. When `API_BEARER_TOKEN` is set, authenticated endpoints require `X-API-Key`.

### Create a recording job

```bash
curl -X POST http://localhost:8000/v1/jobs \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: YOUR_API_BEARER_TOKEN' \
  -d '{"url":"https://www.tiktok.com/@creator/live","telegram_chat_id":123456789,"requester_id":123456789}'
```

Response: `202 Accepted` with `job_id`, `status`, timestamps, elapsed seconds, and URL. The worker probes the LIVE state asynchronously; a non-live page ends as `failed` with an explanation.

### Inspect job / list recent jobs

```bash
curl -H 'X-API-Key: YOUR_API_BEARER_TOKEN' http://localhost:8000/v1/jobs/JOB_ID
curl -H 'X-API-Key: YOUR_API_BEARER_TOKEN' 'http://localhost:8000/v1/jobs?limit=25&requester_id=123456789'
```

- `GET /healthz` — liveness and DB/Redis dependency check
- `POST /v1/jobs` — queue a recording
- `GET /v1/jobs/{job_id}` — inspect one job
- `GET /v1/jobs?limit=50&requester_id=...` — recent jobs
- OpenAPI docs: `/docs`

## Operational settings

- `MAX_RECORDING_HOURS` — worker safety cap (default 12 hours); a recording exceeding it is stopped.
- `MAX_UPLOAD_MB` — conservative Telegram cloud upload ceiling (default 49 MB). Oversized MP4s are transcoded to fit where feasible; very long recordings may still exceed the cap and are reported as failed rather than silently truncated. For larger files, configure and operate a compatible local Telegram Bot API server and set `TELEGRAM_API_BASE` and its permitted upload limit.
- `RETENTION_DAYS` — completed recording files older than this window are pruned when a new recording job starts; job metadata remains in the database. For regular cleanup during idle periods, schedule a maintenance run or add a periodic cleanup service.
- `ALLOWED_TELEGRAM_USER_IDS` — restrict bot commands and API-submitted requester IDs.
- `MAX_JOBS_PER_USER_PER_DAY` — public-use daily cap (default 2); duplicate active requests do not consume another slot.
- `MAX_ACTIVE_JOBS_PER_USER` and `MAX_OPEN_JOBS_TOTAL` — limit each user's active requests (default 1) and the total queue (default 5).
- `KEEP_LOCAL_RECORDINGS=false` — after Telegram confirms delivery, delete local media and logs while keeping job metadata. Set `true` only if you have sufficient storage and want a server-side copy.

The bot never reports a fabricated finish time. A live capture has no reliable ETA until the broadcaster ends the stream. A worker/process outage during a LIVE can interrupt recording; after restart, submit a fresh request because a partially captured live session cannot necessarily be resumed at the original point.

## Temporary Railway Trial deployment

For a no-paid-upgrade Railway Trial deployment, follow [RAILWAY_DEPLOY.md](RAILWAY_DEPLOY.md). Trial credits are limited and a 0.5 GB volume can fail on long/high-bitrate streams; do not upgrade to a paid plan if you want to avoid charges. For **$0 cloud hosting**, run the included Compose stack on your own computer that stays online; follow [FREE_SELF_HOST.md](FREE_SELF_HOST.md).


## Development / testing

Python 3.12+, FFmpeg/ffprobe, yt-dlp, Redis, and PostgreSQL are required. Install Python packages with `pip install -r requirements.txt` and `pip install yt-dlp`, configure `.env`, then run:

```bash
uvicorn app.api:app --host 127.0.0.1 --port 8000
python -m app.bot
python -m app.worker_main
pytest -q
```

Run the three processes in separate terminals. Do not use the sandbox as a 24/7 production host; deploy Compose on a machine that stays online. Back up the Postgres and recordings volumes and review applicable TikTok/Telegram terms, copyright, privacy, and consent requirements.
