from app.db import normalize_database_url


def test_railway_postgres_url_uses_psycopg3():
    assert normalize_database_url("postgres://u:p@host:5432/db") == "postgresql+psycopg://u:p@host:5432/db"
    assert normalize_database_url("postgresql://u:p@host:5432/db") == "postgresql+psycopg://u:p@host:5432/db"


def test_compose_driver_url_is_unchanged():
    value = "postgresql+psycopg://u:p@host:5432/db"
    assert normalize_database_url(value) == value


def test_sqlite_url_is_unchanged():
    value = "sqlite:////data/jobs.sqlite3"
    assert normalize_database_url(value) == value
