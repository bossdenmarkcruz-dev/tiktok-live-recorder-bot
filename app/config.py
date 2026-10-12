from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str = ""
    telegram_api_base: str = "https://api.telegram.org"
    redis_url: str = "redis://redis:6379/0"
    database_url: str = "sqlite:////data/jobs.sqlite3"
    recordings_dir: str = "/data/recordings"
    api_bearer_token: str = ""
    allowed_telegram_user_ids: str = ""
    max_upload_mb: int = 49
    max_recording_hours: int = 12
    probe_timeout_seconds: int = 90
    retention_days: int = 14
    keep_local_recordings: bool = False
    max_jobs_per_user_per_day: int = 2
    max_active_jobs_per_user: int = 1
    max_open_jobs_total: int = 5

    @property
    def allowed_user_ids(self) -> set[int]:
        values = [part.strip() for part in self.allowed_telegram_user_ids.split(",") if part.strip()]
        return {int(value) for value in values}


@lru_cache

def get_settings() -> Settings:
    return Settings()


settings = get_settings()
