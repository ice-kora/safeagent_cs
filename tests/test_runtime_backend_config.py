from app.storage.runtime_config import (
    RUNTIME_BACKEND_POSTGRES,
    RUNTIME_BACKEND_SQLITE,
    get_runtime_database_settings,
    redact_runtime_database_url,
)


def test_default_runtime_backend_is_sqlite(monkeypatch) -> None:
    monkeypatch.delenv("SAFEAGENT_RUNTIME_BACKEND", raising=False)
    monkeypatch.delenv("SAFEAGENT_RUNTIME_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = get_runtime_database_settings()

    assert settings.backend == RUNTIME_BACKEND_SQLITE
    assert settings.database_url is None


def test_invalid_runtime_backend_falls_back_sqlite(monkeypatch) -> None:
    monkeypatch.setenv("SAFEAGENT_RUNTIME_BACKEND", "mysql")

    settings = get_runtime_database_settings()

    assert settings.backend == RUNTIME_BACKEND_SQLITE


def test_runtime_postgres_reads_runtime_database_url(monkeypatch) -> None:
    monkeypatch.setenv("SAFEAGENT_RUNTIME_BACKEND", "postgres")
    monkeypatch.setenv(
        "SAFEAGENT_RUNTIME_DATABASE_URL",
        "postgresql://user:secret@localhost/runtime",
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:other@localhost/platform")

    settings = get_runtime_database_settings()

    assert settings.backend == RUNTIME_BACKEND_POSTGRES
    assert settings.database_url == "postgresql://user:secret@localhost/runtime"


def test_runtime_postgres_falls_back_to_database_url(monkeypatch) -> None:
    monkeypatch.setenv("SAFEAGENT_RUNTIME_BACKEND", "postgres")
    monkeypatch.delenv("SAFEAGENT_RUNTIME_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@localhost/shared")

    settings = get_runtime_database_settings()

    assert settings.database_url == "postgresql://user:secret@localhost/shared"


def test_runtime_database_url_redaction_hides_password() -> None:
    redacted = redact_runtime_database_url(
        "postgresql://user:secret@localhost:5432/runtime"
    )

    assert redacted == "postgresql://user:***@localhost:5432/runtime"
    assert "secret" not in redacted
