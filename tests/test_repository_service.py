from pathlib import Path

import pytest

from app.services.repository_service import RepositoryService


def test_get_user_context_reads_minimal_user_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFEAGENT_DB_BACKEND", "sqlite")
    repository = RepositoryService(db_path=tmp_path / "test.db")

    context = repository.get_user_context("u_1001")

    assert context == {
        "user_id": "u_1001",
        "role": "user",
        "tenant_id": "t_001",
        "status": "ACTIVE",
    }


def test_get_order_auth_context_reads_only_auth_fields(tmp_path: Path) -> None:
    repository = RepositoryService(db_path=tmp_path / "test.db")

    context = repository.get_order_auth_context("O10086")

    assert context == {
        "order_id": "O10086",
        "user_id": "u_1001",
        "tenant_id": "t_001",
        "order_status": "PAID",
        "delivery_status": "PENDING_SHIPMENT",
        "refund_status": "NONE",
    }
    assert "address" not in context
    assert "address_masked" not in context
    assert "phone" not in context
    assert "payment_info" not in context
    assert "amount" not in context


def test_get_open_ticket_by_idempotency_key_returns_open_ticket(
    tmp_path: Path,
) -> None:
    repository = RepositoryService(db_path=tmp_path / "test.db")

    from app.storage.db import get_connection

    with get_connection(repository.db_path) as connection:
        connection.execute(
            """
            INSERT INTO tickets (
                id, user_id, type, status, risk_level,
                idempotency_key, source_run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "tk_existing",
                "u_1001",
                "refund",
                "OPEN",
                "L4",
                "u_1001:request_refund:order:O10086",
                "run_001",
            ),
        )
        connection.commit()

    ticket = repository.get_open_ticket_by_idempotency_key(
        "u_1001:request_refund:order:O10086"
    )

    assert ticket is not None
    assert ticket["id"] == "tk_existing"
    assert ticket["status"] == "OPEN"


def test_missing_mock_file_reports_clear_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFEAGENT_DB_BACKEND", "sqlite")
    repository = RepositoryService(
        mock_dir=tmp_path / "missing_mock_dir",
        db_path=tmp_path / "test.db",
    )

    with pytest.raises(RuntimeError, match="Mock data file not found"):
        repository.get_user_context("u_1001")
