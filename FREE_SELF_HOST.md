# Run the bot for free on your own computer

This is the realistic no-monthly-hosting-cost option for recording whole TikTok LIVE streams. It uses the computer and disk you already own. The bot is online only while that computer is powered on, connected to the internet, and Docker is running.

## What you need

- A Windows, macOS, or Linux computer that can stay on during streams.
- Docker Desktop (Windows/macOS) or Docker Engine plus the Compose plugin (Linux).
- Enough free disk space for recordings. Long streams can use substantial storage; the bot's 49 MB Telegram upload limit does not limit the temporary source file stored on your computer.
- A Telegram bot token from **@BotFather**. Keep it private.

No public IP address or router port-forwarding is needed for Telegram bot polling. The API is bound to `127.0.0.1:8000` by default and is not exposed to the internet.

## Setup

1. Sign into GitHub and download or clone the private repo: <https://github.com/bossdenmarkcruz-dev/tiktok-live-recorder-bot>.
2. Install and start Docker Desktop / Docker Engine.
3. In the project directory, copy `.env.example` to `.env`:
   - Windows PowerShell: `Copy-Item .env.example .env`
   - macOS/Linux: `cp .env.example .env`
4. Open `.env` in a text editor and set:
   - `TELEGRAM_BOT_TOKEN` — the token from BotFather.
   - `POSTGRES_PASSWORD` — a strong random alphanumeric secret (hex is convenient).
   - `API_BEARER_TOKEN` — another long random secret.
- `ALLOWED_TELEGRAM_USER_IDS` — your numeric Telegram user ID. Do not leave it blank for a private bot; use a trusted Telegram ID lookup bot such as `@userinfobot` if needed.
- For a public bot, the blank allowlist intentionally permits anyone to use it. The default safeguards allow at most two requests per user per 24 hours, one open request per user, and five open jobs globally. Do not remove these limits on a free/limited host.
5. Save `.env`. Do not upload or commit it.
6. Start the bot stack from that project directory:

   ```sh
   docker compose up -d --build
   docker compose ps
   docker compose logs -f bot worker api
   ```

7. When the containers are healthy, open the bot in Telegram and send `/start`, then test with a LIVE URL for a stream you own or have permission to record.

## Keep it available

- Keep the computer awake and online while a LIVE is being recorded. Sleep, shutdown, internet loss, or Docker stopping can interrupt a recording.
- Enable Docker Desktop to start when you sign in. On Linux, enable Docker to start at boot. Compose uses `restart: unless-stopped` so containers restart when the Docker service returns.
- Watch free disk space and back up the Docker volumes if the recordings/job history matter. The configured 14-day cleanup runs when a new recording starts, not on a fixed schedule.
- By default, the bot deletes local media and logs after Telegram confirms delivery; job history remains. A single source recording still needs enough temporary disk space while it is downloading and processing.
- To stop the stack: `docker compose down`. To stop it and delete all database, queue, and recording data: `docker compose down -v` (destructive; do not run unless you intend to erase that data).

## Troubleshooting

- `docker compose ps` shows service state.
- `docker compose logs -f bot worker api` shows bot and recorder errors.
- Check the local API health endpoint with `curl http://127.0.0.1:8000/healthz` (or visit that URL in a browser).
- If the bot says it is not configured, check the token in `.env`, then restart with `docker compose up -d`.

This setup costs **$0 in hosting charges** because it uses your existing computer. Electricity, internet, hardware, and disk are still your responsibility. It is not independent of your computer, and it is not a cloud-hosted 24/7 service.
