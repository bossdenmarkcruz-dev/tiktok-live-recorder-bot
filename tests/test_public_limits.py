import pytest
from app.domain import JobQuotaExceeded, enforce_public_job_limits
from app.config import settings


def test_allows_request_under_public_limits():
    enforce_public_job_limits(user_active=0, total_open=0, user_last_day=0)


def test_blocks_second_active_request_from_same_user():
    with pytest.raises(JobQuotaExceeded, match="already have a recording"):
        enforce_public_job_limits(user_active=settings.max_active_jobs_per_user, total_open=1, user_last_day=1)


def test_blocks_when_public_queue_is_full():
    with pytest.raises(JobQuotaExceeded, match="queue is full"):
        enforce_public_job_limits(user_active=0, total_open=settings.max_open_jobs_total, user_last_day=0)


def test_blocks_daily_user_limit():
    with pytest.raises(JobQuotaExceeded, match="every 24 hours"):
        enforce_public_job_limits(user_active=0, total_open=0, user_last_day=settings.max_jobs_per_user_per_day)
