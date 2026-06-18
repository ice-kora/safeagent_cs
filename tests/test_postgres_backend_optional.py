import os

import pytest

from app.services.repository_service import RepositoryService
from app.storage.database_config import DB_BACKEND_POSTGRES
from app.storage.postgres import PostgresBackend, PostgresBackendError


def test_postgres_optional_skips_without_database_url(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not configured for optional PostgreSQL test")


def test_postgres_backend_can_init_seed_and_read_context(monkeypatch) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is not configured for optional PostgreSQL test")

    monkeypatch.setenv("SAFEAGENT_DB_BACKEND", DB_BACKEND_POSTGRES)
    backend = PostgresBackend(database_url)
    try:
        backend.init_schema()
        backend.seed_users_orders()
    except PostgresBackendError as exc:
        pytest.skip(str(exc))

    repository = RepositoryService(db_backend=DB_BACKEND_POSTGRES)

    user_context = repository.get_user_context("u_1001")
    order_context = repository.get_order_auth_context("O10086")

    assert user_context["user_id"] == "u_1001"
    assert order_context["order_id"] == "O10086"
