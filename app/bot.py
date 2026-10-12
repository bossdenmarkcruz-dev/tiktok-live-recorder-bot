import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from app.config import settings
from app.db import SessionLocal, init_db
from app.domain import InvalidTikTokLiveURL, create_job
from app.models import RecordingJob
from app.queueing import enqueue_recording

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("telegram-bot")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        'Send /download_replay "https://www.tiktok.com/@creator/live" while the LIVE is active.\n'
        "The bot records from the moment it joins and sends the MP4 after the stream ends. "
        "It cannot predict the exact end time or recover video from before recording began.\n\n"
        "Use /status JOB_ID to check progress."
    )


async def download_replay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    if settings.allowed_user_ids and user.id not in settings.allowed_user_ids:
        await msg.reply_text("You are not authorized to use this bot.")
        return
    raw = msg.text.partition(" ")[2].strip() if msg.text else ""
    if not raw:
        await msg.reply_text('Usage: /download_replay "https://www.tiktok.com/@creator/live"')
        return
    try:
        job, created = create_job(raw, update.effective_chat.id, user.id)
        if created:
            try:
                rq_id = enqueue_recording(job.id)
            except Exception:
                with SessionLocal() as db:
                    stored = db.get(RecordingJob, job.id)
                    if stored:
                        stored.status = "failed"
                        stored.error = "Queue unavailable; retry later."
                        db.commit()
                raise
            with SessionLocal() as db:
                stored = db.get(RecordingJob, job.id)
                stored.rq_job_id = rq_id
                db.commit()
            await msg.reply_text(
                f"Recording request queued. Job ID: {job.id}\n"
                "I will check that the URL is a currently active TikTok LIVE. If it is live, recording starts now. "
                "The finish time is unknown; use /status <job_id> for elapsed time."
            )
        else:
            await msg.reply_text(f"That URL already has an active job: {job.id}\nUse /status {job.id}")
    except InvalidTikTokLiveURL as exc:
        await msg.reply_text(str(exc))
    except Exception:
        log.exception("Could not queue recording")
        await msg.reply_text("Could not queue this job right now. Please try again in a moment.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, msg = update.effective_user, update.effective_message
    if not user or not msg:
        return
    if settings.allowed_user_ids and user.id not in settings.allowed_user_ids:
        await msg.reply_text("You are not authorized to use this bot.")
        return
    job_id = context.args[0] if context.args else ""
    if not job_id:
        await msg.reply_text("Usage: /status <job_id>")
        return
    with SessionLocal() as db:
        job = db.get(RecordingJob, job_id)
        if not job or (job.requester_id != user.id and user.id not in settings.allowed_user_ids):
            await msg.reply_text("Job not found.")
            return
        elapsed = max(0, int(job.elapsed_seconds or 0))
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        eta = "unknown — the broadcaster controls when the LIVE ends"
        await msg.reply_text(
            f"Job: {job.id}\nStatus: {job.status}\nRecording elapsed: {hours:02d}:{minutes:02d}:{seconds:02d}\n"
            f"Finish ETA: {eta}" + (f"\nDetails: {job.error}" if job.error else "")
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


def main() -> None:
    if not settings.telegram_bot_token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env before starting the bot")
    init_db()
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("download_replay", download_replay))
    app.add_handler(CommandHandler("status", status))
    log.info("Starting Telegram long-polling bot")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
