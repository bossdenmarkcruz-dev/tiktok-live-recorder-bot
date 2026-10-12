import glob
import json
import logging
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests
from sqlalchemy import select
from app.config import settings
from app.db import SessionLocal, init_db
from app.models import RecordingJob

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("recorder-worker")


def now() -> datetime:
    return datetime.now(timezone.utc)


def update_job(job_id: str, **changes) -> None:
    with SessionLocal() as db:
        job = db.get(RecordingJob, job_id)
        if job:
            for key, value in changes.items():
                setattr(job, key, value)
            db.commit()


def get_job(job_id: str) -> RecordingJob | None:
    with SessionLocal() as db:
        return db.get(RecordingJob, job_id)


def delete_job_files(job_id: str, output_path: str | None = None) -> None:
    generated = set(glob.glob(os.path.join(settings.recordings_dir, f"{job_id}.*")))
    generated.update(glob.glob(os.path.join(settings.recordings_dir, f"{job_id}-*")))
    generated.add(os.path.join(settings.recordings_dir, f"{job_id}.log"))
    if output_path:
        generated.add(output_path)
    for path in generated:
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                log.warning("Could not remove recording file %s", path)


def prune_old_recordings() -> None:
    """Delete media past retention while keeping job metadata for history."""
    cutoff = now() - timedelta(days=max(1, settings.retention_days))
    with SessionLocal() as db:
        expired = db.scalars(select(RecordingJob).where(
            RecordingJob.status == "completed",
            RecordingJob.finished_at < cutoff,
        )).all()
        for job in expired:
            delete_job_files(job.id, job.output_path)
            job.output_path = None
            job.file_size = None
        if expired:
            db.commit()
            log.info("Pruned media for %d expired recording job(s)", len(expired))


def telegram(method: str, *, data=None, files=None, timeout=30) -> dict:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    url = f"{settings.telegram_api_base.rstrip('/')}/bot{settings.telegram_bot_token}/{method}"
    response = requests.post(url, data=data, files=files, timeout=timeout)
    try:
        payload = response.json()
    except ValueError:
        payload = {"ok": False, "description": response.text[:500]}
    if response.status_code >= 400 or not payload.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {payload.get('description', response.status_code)}")
    return payload


def notify(chat_id: int, text: str) -> None:
    try:
        telegram("sendMessage", data={"chat_id": chat_id, "text": text}, timeout=30)
    except Exception:
        log.exception("Could not send Telegram status message")


def fail(job_id: str, message: str, chat_id: int | None = None) -> None:
    update_job(job_id, status="failed", error=message[:4000], finished_at=now())
    if chat_id is not None:
        notify(chat_id, f"Recording job {job_id} failed: {message[:800]}")


def probe_live(url: str) -> dict:
    result = subprocess.run(
        ["yt-dlp", "--no-warnings", "--no-playlist", "--skip-download", "--dump-single-json", url],
        capture_output=True, text=True, timeout=settings.probe_timeout_seconds, check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        detail = (result.stderr or "No stream metadata returned.").strip()[-1000:]
        raise RuntimeError(f"TikTok could not provide live metadata: {detail}")
    try:
        info = json.loads(result.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("TikTok returned unreadable stream metadata.") from exc
    extractor = (info.get("extractor_key") or info.get("extractor") or "").lower()
    if "tiktok" not in extractor:
        raise RuntimeError("The URL did not resolve to a TikTok stream.")
    live_status = (info.get("live_status") or "").lower()
    if not info.get("is_live") and live_status not in {"is_live", "live"}:
        raise RuntimeError("This TikTok page is not currently live. Submit the command again while the LIVE is active.")
    return info


def probe_duration(path: str) -> float:
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path], capture_output=True, text=True, timeout=30, check=True)
        return float(json.loads(result.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def ensure_mp4(path: str, job_id: str) -> str:
    if Path(path).suffix.lower() == ".mp4":
        return path
    output = str(Path(path).with_name(f"{job_id}-normalized.mp4"))
    remux = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", path, "-c", "copy", "-movflags", "+faststart", output], capture_output=True, text=True, timeout=1800, check=False)
    if remux.returncode != 0 or not os.path.exists(output):
        transcode = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", path, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", output], capture_output=True, text=True, timeout=7200, check=False)
        if transcode.returncode != 0 or not os.path.exists(output):
            raise RuntimeError(f"Could not convert the stream to MP4: {(transcode.stderr or remux.stderr or '')[-700:]}")
    return output


def compress_to_limit(path: str, job_id: str) -> str:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if os.path.getsize(path) <= max_bytes:
        return path
    duration = probe_duration(path)
    if duration <= 0:
        raise RuntimeError("The recording is too large for Telegram, and its duration could not be read for compression.")
    target_total_bps = int((max_bytes * 8 * 0.90) / duration)
    video_bps = target_total_bps - 96_000
    if video_bps < 250_000:
        raise RuntimeError(f"The recording exceeds Telegram's configured {settings.max_upload_mb} MB upload limit and is too long to compress safely.")
    output = str(Path(path).with_name(f"{job_id}-telegram.mp4"))
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", path,
        "-vf", "scale=w='min(1280,iw)':h=-2", "-c:v", "libx264", "-preset", "veryfast",
        "-b:v", str(video_bps), "-maxrate", str(video_bps), "-bufsize", str(video_bps * 2),
        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", output,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=max(600, int(duration * 2)), check=False)
    if result.returncode != 0 or not os.path.exists(output):
        raise RuntimeError(f"Could not compress the recording for Telegram: {(result.stderr or '')[-700:]}")
    if os.path.getsize(output) > max_bytes:
        raise RuntimeError(f"The recording still exceeds Telegram's configured {settings.max_upload_mb} MB limit after compression.")
    return output


def upload_recording(job: RecordingJob, path: str, elapsed: int) -> str:
    path = compress_to_limit(ensure_mp4(path, job.id), job.id)
    size = os.path.getsize(path)
    if size > settings.max_upload_mb * 1024 * 1024:
        raise RuntimeError(f"File is larger than the configured {settings.max_upload_mb} MB Telegram upload limit.")
    caption = f"TikTok LIVE recording complete · {elapsed // 60} min recorded · job {job.id[:8]}"
    with open(path, "rb") as media:
        telegram("sendVideo", data={"chat_id": job.chat_id, "caption": caption, "supports_streaming": "true"}, files={"video": (os.path.basename(path), media, "video/mp4")}, timeout=(30, 1800))
    return path


def record_and_deliver(job_id: str) -> str:
    init_db()
    job = get_job(job_id)
    if not job:
        raise RuntimeError(f"Unknown recording job {job_id}")
    os.makedirs(settings.recordings_dir, exist_ok=True)
    prune_old_recordings()
    update_job(job_id, status="checking", error=None)
    log.info("Checking LIVE state for job %s", job_id)
    try:
        probe_live(job.url)
        started = now()
        started_clock = time.monotonic()
        update_job(job_id, status="recording", started_at=started, elapsed_seconds=0)
        notify(job.chat_id, f"TikTok LIVE is active. Recording has started for job {job_id}.\nThe stream end time is controlled by the broadcaster, so an exact ETA is unavailable. I will send the video when recording stops.")
        output_template = os.path.join(settings.recordings_dir, f"{job_id}.%(ext)s")
        log_path = os.path.join(settings.recordings_dir, f"{job_id}.log")
        command = ["yt-dlp", "--no-warnings", "--no-playlist", "--no-part", "--newline", "--merge-output-format", "mp4", "-f", "best", "-o", output_template, job.url]
        with open(log_path, "w", encoding="utf-8") as log_file:
            process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT)
            max_seconds = settings.max_recording_hours * 3600
            while process.poll() is None:
                elapsed = int(time.monotonic() - started_clock)
                update_job(job_id, elapsed_seconds=elapsed)
                if elapsed >= max_seconds:
                    process.terminate()
                    try:
                        process.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise RuntimeError(f"Configured recording cap of {settings.max_recording_hours} hours reached.")
                time.sleep(15)
            exit_code = process.returncode
        elapsed = int(time.monotonic() - started_clock)
        update_job(job_id, elapsed_seconds=elapsed, status="processing")
        if exit_code != 0:
            with open(log_path, "r", encoding="utf-8", errors="replace") as logfile:
                tail = logfile.read()[-1200:]
            raise RuntimeError(f"Recorder exited with code {exit_code}. {tail.strip()}")
        candidates = [p for p in glob.glob(os.path.join(settings.recordings_dir, f"{job_id}.*")) if not p.endswith((".log", ".part", ".ytdl")) and os.path.isfile(p)]
        if not candidates:
            raise RuntimeError("The livestream ended but no playable recording file was produced.")
        media_path = max(candidates, key=os.path.getsize)
        update_job(job_id, output_path=media_path, file_size=os.path.getsize(media_path), status="sending")
        delivered_path = upload_recording(job, media_path, elapsed)
        final_size = os.path.getsize(delivered_path)
        stored_path = delivered_path
        if not settings.keep_local_recordings:
            delete_job_files(job_id, delivered_path)
            stored_path = None
        update_job(job_id, status="completed", finished_at=now(), output_path=stored_path, file_size=final_size, error=None)
        notify(job.chat_id, f"Recording delivered. Job {job_id} completed in {elapsed // 60} minutes.")
        return delivered_path
    except Exception as exc:
        log.exception("Recording job %s failed", job_id)
        fail(job_id, str(exc), job.chat_id)
        return "failed"
