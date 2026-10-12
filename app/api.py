import hmac
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from app.config import settings
from app.db import SessionLocal, init_db
from app.domain import InvalidTikTokLiveURL, JobQuotaExceeded, create_job, public_job
from app.models import RecordingJob
from app.queueing import enqueue_recording, redis_connection

app = FastAPI(title="TikTok LIVE Recorder API", version="1.0.0", description="Queue and inspect authorized TikTok LIVE recording jobs.")


class CreateJobRequest(BaseModel):
    url: str = Field(min_length=10, max_length=2048)
    telegram_chat_id: int
    requester_id: int


def authorize(x_api_key: str | None = Header(default=None)) -> None:
    if not settings.api_bearer_token:
        return  # Convenient for local development; set API_BEARER_TOKEN in any exposed deployment.
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_bearer_token):
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/healthz")
def healthz() -> dict:
    try:
        redis_connection().ping()
        with SessionLocal() as db:
            db.execute(select(1))
        return {"status": "ok", "database": "ok", "redis": "ok", "time": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Dependency check failed: {type(exc).__name__}") from exc


@app.post("/v1/jobs", status_code=202, dependencies=[Depends(authorize)])
def submit_job(request: CreateJobRequest) -> dict:
    if settings.allowed_user_ids and request.requester_id not in settings.allowed_user_ids:
        raise HTTPException(status_code=403, detail="Requester is not authorized")
    try:
        job, created = create_job(request.url, request.telegram_chat_id, request.requester_id)
    except InvalidTikTokLiveURL as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except JobQuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if created:
        try:
            rq_id = enqueue_recording(job.id)
            with SessionLocal() as db:
                stored = db.get(RecordingJob, job.id)
                stored.rq_job_id = rq_id
                db.commit()
        except Exception as exc:
            with SessionLocal() as db:
                stored = db.get(RecordingJob, job.id)
                if stored:
                    stored.status = "failed"
                    stored.error = "Queue unavailable; retry later."
                    stored.finished_at = datetime.now(timezone.utc)
                    db.commit()
            raise HTTPException(status_code=503, detail="Recording queue unavailable") from exc
    return {**public_job(job), "created": created}


@app.get("/v1/jobs/{job_id}", dependencies=[Depends(authorize)])
def get_job(job_id: str) -> dict:
    with SessionLocal() as db:
        job = db.get(RecordingJob, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return public_job(job)


@app.get("/v1/jobs", dependencies=[Depends(authorize)])
def list_jobs(limit: int = 50, requester_id: int | None = None) -> dict:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    statement = select(RecordingJob).order_by(RecordingJob.created_at.desc()).limit(limit)
    if requester_id is not None:
        statement = statement.where(RecordingJob.requester_id == requester_id)
    with SessionLocal() as db:
        jobs = db.scalars(statement).all()
        return {"jobs": [public_job(job) for job in jobs]}
