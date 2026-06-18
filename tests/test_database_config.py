from app.storage.database_config import (
    DB_BACKEND_POSTGRES,
    DB_BACKEND_SQLITE,
    get_database_settings,
    redact_database_url,
)


def test_default_backend_is_sqlite(monkeypatch) -> None:
    monkeypatch.delenv("SAFEAGENT_DB_BACKEND", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = get_database_settings()

    assert settings.backend == DB_BACKEND_SQLITE
    assert settings.database_url is None


def test_invalid_backend_falls_back_sqlite(monkeypatch) -> None:
    monkeypatch.setenv("SAFEAGENT_DB_BACKEND", "oracle")

    settings = get_database_settings()

    assert settings.backend == DB_BACKEND_SQLITE


def test_postgres_backend_reads_database_url(monkeypatch) -> None:
    monkeypatch.setenv("SAFEAGENT_DB_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@localhost/db")

    settings = get_database_settings()

    assert settings.backend == DB_BACKEND_POSTGRES
    assert settings.database_url == "postgresql://user:secret@localhost/db"


def test_redact_database_url_hides_password() -> None:
    redacted = redact_database_url("postgresql://user:secret@localhost:5432/db")

    assert redacted == "postgresql://user:***@localhost:5432/db"
    assert "secret" not in redacted
