# Temporary Railway Trial deployment

This repository can run on Railway during the account's no-charge Trial as five services: **API**, **Telegram bot**, **recording worker**, **PostgreSQL**, and **Redis**. Railway does not run `docker-compose.yml` directly; create each service separately using the same repository and Dockerfile.

## No-charge boundary and Trial limits

Railway currently grants a one-time **$5 Trial credit for up to 30 days**. When it is spent or expires, the account reverts to the **Free** plan with **$1 of monthly credit**. Services can be stopped when the usage limit is reached. **Do not upgrade to Hobby, add a paid commitment, or enable paid resources.** This does not authorize any charge.

Trial limits include five services per project and **0.5 GB of volume storage**. That disk is only enough for shorter/smaller streams. A long or high-bitrate LIVE can fill the volume before it ends. After delivery, local media is deleted by default, but the entire source recording still has to fit while it is being captured and processed. Public traffic can use the $5 credit quickly, so the service may stop before 30 days.

Railway says Trial volumes are deleted **30 days after Trial credits expire**. Migrate any data you need before that deadline; this is not archival storage.

The account must have a Full Trial for unrestricted outbound network access to TikTok and Telegram. Railway says connecting and verifying the GitHub account is part of Full Trial verification. If the account remains Limited Trial, outbound network restrictions may prevent recording or delivery.

## Create the services

Use the existing empty project. Connect the private GitHub repository `bossdenmarkcruz-dev/tiktok-live-recorder-bot` on branch `main`. If Railway asks, authorize its GitHub App for this repository. Use the repository-root `Dockerfile` for the three application services.

### 1. PostgreSQL and 2. Redis

Add Railway PostgreSQL and Redis services. Set `DATABASE_URL` and `REDIS_URL` in the API, Telegram bot, and recording worker using Railway reference variables to those services. The app converts generic PostgreSQL URLs to the installed psycopg v3 driver.

### 3. API service

Use the Dockerfile's default command. Keep this service **private**; the Telegram bot does not require a public API domain. Set:

- `DATABASE_URL` — Railway PostgreSQL reference
- `REDIS_URL` — Railway Redis reference
- `API_BEARER_TOKEN` — a long random secret
- `RECORDINGS_DIR=/data/recordings`
- `ALLOWED_TELEGRAM_USER_IDS=` — leave empty only if you intend public Telegram access
- `MAX_JOBS_PER_USER_PER_DAY=2`
- `MAX_ACTIVE_JOBS_PER_USER=1`
- `MAX_OPEN_JOBS_TOTAL=5`
- `KEEP_LOCAL_RECORDINGS=false`
- `MAX_UPLOAD_MB=49`
- `MAX_RECORDING_HOURS=12`
- `RETENTION_DAYS=14`

### 4. Telegram bot service

Use the same repository and Dockerfile. Set its start command to:

```sh
python -m app.bot
```

Set the PostgreSQL and Redis reference variables, `TELEGRAM_BOT_TOKEN`, and the same public quota variables listed above. Leaving `ALLOWED_TELEGRAM_USER_IDS` empty allows anyone on Telegram to use the bot, while the rate limits remain active.

### 5. Recording worker service

Use the same repository and Dockerfile. Set its start command to:

```sh
python -m app.worker_main
```

Set PostgreSQL and Redis references, `TELEGRAM_BOT_TOKEN`, and the public quota variables. Add one volume mounted at `/data/recordings`; keep one worker replica. The current Trial volume limit is 0.5 GB. `KEEP_LOCAL_RECORDINGS=false` deletes each local recording after Telegram confirms it was sent.

The BotFather token is needed by the Telegram bot and the worker. Enter it directly in Railway's secret variable fields; never commit it or send it in chat.

## Check it

1. Ensure the account is still on Trial and the usage page shows no paid plan. Do not upgrade to Hobby.
2. Deploy Postgres, Redis, API, bot, and worker. Confirm all five services start. The API does not need a public domain.
3. Send `/start` to the bot. For a test, submit only a LIVE you own or are authorized to record.
4. Check Railway Trial usage and the worker volume. A public user can spend trial resources; the daily quota, one open job per user, five-job total queue cap, 12-hour recording cap, and delete-after-delivery setting are important safeguards.
5. When Railway stops services because the Trial credit/time expires, leave the project on Free. Do not upgrade. Use the [local self-host guide](FREE_SELF_HOST.md) temporarily or migrate to your own VPS when you have one.
