from pathlib import Path

from app.storage.db import get_connection
from app.storage.db import init_db
from app.tools.ticket_tool import create_ticket


def _ticket_count(db_path: Path) -> int:
    init_db(db_path)
    with get_connection(db_path) as connection:
        return connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]


def test_create_ticket_returns_ticket_id_and_safe_summary(tmp_path: Path) -> None:
    result = create_ticket(
        user_id="u_1001",
        action="request_refund",
        target_type="order",
        target_id="O10086",
        ticket_type="refund",
        description="我要退款，手机号 13800001234",
        db_path=tmp_path / "test.db",
        source_run_id="run_001",
    )

    assert result.success is True
    assert result.tool_name == "ticket_tool.create_ticket"
    assert result.data["ticket_id"].startswith("tk_")
    assert result.data["status"] == "OPEN"
    assert result.data["created"] is True
    assert "13800001234" not in result.summary


def test_create_ticket_reuses_existing_open_ticket_by_idempotency_key(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"
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
    assert "不重复创建" in second.summary


def test_create_ticket_allows_new_ticket_after_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    first = create_ticket(
        user_id="u_1001",
        action="request_refund",
        target_type="order",
        target_id="O10086",
        ticket_type="refund",
        db_path=db_path,
    )
    with get_connection(db_path) as connection:
        connection.execute(
            "UPDATE tickets SET status = 'CLOSED' WHERE id = ?",
            (first.data["ticket_id"],),
        )
        connection.commit()

    second = create_ticket(
        user_id="u_1001",
        action="request_refund",
        target_type="order",
        target_id="O10086",
        ticket_type="refund",
        db_path=db_path,
    )

    assert second.success is True
    assert second.data["ticket_id"] != first.data["ticket_id"]
    assert second.data["created"] is True


def test_create_ticket_missing_user_id_does_not_write_ticket(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"

    result = create_ticket(
        user_id="",
        action="request_refund",
        target_type="order",
        target_id="O10086",
        ticket_type="refund",
        db_path=db_path,
    )

    assert result.success is False
    assert result.error_type == "TICKET_ARGS_INVALID"
    assert result.summary == "创建工单缺少必要参数。"
    assert _ticket_count(db_path) == 0


def test_create_ticket_missing_action_does_not_write_ticket(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"

    result = create_ticket(
        user_id="u_1001",
        action="",
        target_type="order",
        target_id="O10086",
        ticket_type="refund",
        db_path=db_path,
    )

    assert result.success is False
    assert result.error_type == "TICKET_ARGS_INVALID"
    assert _ticket_count(db_path) == 0


def test_create_ticket_missing_target_type_does_not_write_ticket(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"

    result = create_ticket(
        user_id="u_1001",
        action="request_refund",
        target_type="",
        target_id="O10086",
        ticket_type="refund",
        db_path=db_path,
    )

    assert result.success is False
    assert result.error_type == "TICKET_ARGS_INVALID"
    assert _ticket_count(db_path) == 0


def test_create_ticket_refund_order_missing_target_id_does_not_write_ticket(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "test.db"

    result = create_ticket(
        user_id="u_1001",
        action="request_refund",
        target_type="order",
        target_id=None,
        ticket_type="refund",
        db_path=db_path,
    )

    assert result.success is False
    assert result.error_type == "TICKET_ARGS_INVALID"
    assert _ticket_count(db_path) == 0


def test_create_ticket_complete_args_still_create_ticket(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"

    result = create_ticket(
        user_id="u_1001",
        action="request_refund",
        target_type="order",
        target_id="O10086",
        ticket_type="refund",
        db_path=db_path,
    )

    assert result.success is True
    assert result.data["ticket_id"].startswith("tk_")
    assert _ticket_count(db_path) == 1
