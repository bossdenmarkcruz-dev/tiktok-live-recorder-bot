import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from sqlalchemy import func, select
from app.config import settings
from app.db import SessionLocal
from app.models import RecordingJob

ALLOWED_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}


class InvalidTikTokLiveURL(ValueError):
    pass


class JobQuotaExceeded(ValueError):
    pass


ACTIVE_STATUSES = ["queued", "checking", "recording", "processing", "sending"]


def validate_tiktok_live_url(raw_url: str) -> str:
    value = raw_url.strip().strip("\"'")
    if len(value) > 2048:
        raise InvalidTikTokLiveURL("The URL is too long.")
    parsed = urlparse(value)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise InvalidTikTokLiveURL("Send a complete TikTok LIVE URL, such as https://www.tiktok.com/@creator/live")
    host = parsed.hostname.lower().rstrip(".")
    if host not in ALLOWED_HOSTS:
        raise InvalidTikTokLiveURL("Only direct TikTok URLs are accepted; third-party and short links are not allowed.")
    if parsed.username or parsed.password or parsed.port not in (None, 80, 443):
        raise InvalidTikTokLiveURL("That URL contains an unsupported authority or port.")
    if not parsed.path.startswith("/@"):
        raise InvalidTikTokLiveURL("The URL must point to a TikTok LIVE page, for example /@creator/live.")
    # Restrict path shape so profile/video URLs cannot accidentally be queued.
    pieces = [piece for piece in parsed.path.split("/") if piece]
    if len(pieces) != 2 or not pieces[0].startswith("@") or pieces[1] != "live":
        raise InvalidTikTokLiveURL("The URL must point directly to a TikTok LIVE page, for example /@creator/live.")
    return value


def create_job(url: str, chat_id: int, requester_id: int) -> tuple[RecordingJob, bool]:
    normalized = validate_tiktok_live_url(url)
    with SessionLocal() as db:
        existing = db.scalar(select(RecordingJob).where(
            RecordingJob.chat_id == chat_id,
            RecordingJob.requester_id == requester_id,
            RecordingJob.url == normalized,
            RecordingJob.status.in_(["queued", "checking", "recording", "processing", "sending"]),
        ).order_by(RecordingJob.created_at.desc()))
        if existing:
            return existing, False
        user_active = db.scalar(select(func.count()).select_from(RecordingJob).where(
            RecordingJob.requester_id == requester_id,
            RecordingJob.status.in_(ACTIVE_STATUSES),
        )) or 0
        total_open = db.scalar(select(func.count()).select_from(RecordingJob).where(
            RecordingJob.status.in_(ACTIVE_STATUSES),
        )) or 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        user_last_day = db.scalar(select(func.count()).select_from(RecordingJob).where(
            RecordingJob.requester_id == requester_id,
            RecordingJob.created_at >= cutoff,
        )) or 0
        enforce_public_job_limits(user_active, total_open, user_last_day)
        job = RecordingJob(id=str(uuid.uuid4()), chat_id=chat_id, requester_id=requester_id, url=normalized)
        db.add(job)
        db.commit()
        db.refresh(job)
        return job, True


def enforce_public_job_limits(user_active: int, total_open: int, user_last_day: int) -> None:
    if user_active >= settings.max_active_jobs_per_user:
        raise JobQuotaExceeded("You already have a recording request in progress. Wait for it to finish before adding another.")
    if total_open >= settings.max_open_jobs_total:
        raise JobQuotaExceeded("The public recording queue is full right now. Please try again later.")
    if user_last_day >= settings.max_jobs_per_user_per_day:
        raise JobQuotaExceeded(f"Public use is limited to {settings.max_jobs_per_user_per_day} recording requests per user every 24 hours.")


def public_job(job: RecordingJob) -> dict:
    return {
        "job_id": job.id,
        "status": job.status,
        "url": job.url,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "elapsed_seconds": job.elapsed_seconds,
        "file_size_bytes": job.file_size,
        "error": job.error,
    }
