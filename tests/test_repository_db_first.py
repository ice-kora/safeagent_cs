import json
from pathlib import Path

from app.services.repository_service import RepositoryService
from app.storage.db import get_connection, init_db
from app.storage.seed_data import seed_sqlite_users_orders


def test_seeded_user_context_reads_from_db(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SAFEAGENT_DB_BACKEND", raising=False)
    db_path = tmp_path / "test.db"
    seed_sqlite_users_orders(db_path)
    repository = RepositoryService(db_path=db_path)

    context = repository.get_user_context("u_1001")

    assert context == {
        "user_id": "u_1001",
        "role": "customer",
        "tenant_id": "t_001",
        "status": "ACTIVE",
    }


def test_seeded_order_context_reads_from_db(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SAFEAGENT_DB_BACKEND", raising=False)
    db_path = tmp_path / "test.db"
    seed_sqlite_users_orders(db_path)
    repository = RepositoryService(db_path=db_path)

    context = repository.get_order_auth_context("O10086")

    assert context == {
        "order_id": "O10086",
        "user_id": "u_1001",
        "tenant_id": "t_001",
        "order_status": "PAID",
        "delivery_status": "PENDING_SHIPMENT",
        "refund_status": "NONE",
    }


def test_db_data_has_priority_over_mock_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SAFEAGENT_DB_BACKEND", raising=False)
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO users (id, role, tenant_id, status, created_at, updated_at)
            VALUES ('u_1001', 'db_customer', 't_db', 'ACTIVE',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        connection.commit()
    repository = RepositoryService(db_path=db_path)

    context = repository.get_user_context("u_1001")

    assert context["role"] == "db_customer"
    assert context["tenant_id"] == "t_db"


def test_db_empty_falls_back_to_mock_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SAFEAGENT_DB_BACKEND", raising=False)
    repository = RepositoryService(db_path=tmp_path / "test.db")

    context = repository.get_order_auth_context("O10086")

    assert context is not None
    assert context["order_id"] == "O10086"
    assert context["user_id"] == "u_1001"


def test_repository_returns_minimal_fields_without_sensitive_data(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SAFEAGENT_DB_BACKEND", raising=False)
    db_path = tmp_path / "test.db"
    seed_sqlite_users_orders(db_path)
    repository = RepositoryService(db_path=db_path)

    user_context = repository.get_user_context("u_1001")
    order_context = repository.get_order_auth_context("O10086")
    combined = json.dumps(
        {"user": user_context, "order": order_context},
        ensure_ascii=False,
    )

    assert set(user_context) == {"user_id", "role", "tenant_id", "status"}
    assert set(order_context) == {
        "order_id",
        "user_id",
        "tenant_id",
        "order_status",
        "delivery_status",
        "refund_status",
    }
    assert "phone" not in combined
    assert "address" not in combined
    assert "payment_info" not in combined
