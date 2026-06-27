from pathlib import Path

from app.services.repository_service import RepositoryService
from app.tools.ticket_tool import create_ticket


def test_ticket_tool_uses_sqlite_runtime_store(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"

    result = create_ticket(
        user_id="u_1001",
        action="request_refund",
        target_type="order",
        target_id="O10086",
        ticket_type="refund",
        db_path=db_path,
        source_run_id="run_001",
    )
    existing = RepositoryService(db_path=db_path).get_open_ticket_by_idempotency_key(
        "u_1001:request_refund:order:O10086"
    )

    assert result.success is True
    assert existing["id"] == result.data["ticket_id"]


def test_ticket_tool_keeps_open_ticket_idempotency(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"

    first = create_ticket(
        user_id="u_1001",
        action="request_refund",
        target_type="order",
        target_id="O10086",
        ticket_type="refund",
        db_path=db_path,
    )
    second = create_ticket(
        user_id="u_1001",
        action="request_refund",
        target_type="order",
        target_id="O10086",
        ticket_type="refund",
        db_path=db_path,
    )

    assert second.success is True
    assert second.data["ticket_id"] == first.data["ticket_id"]
    assert second.data["created"] is False
