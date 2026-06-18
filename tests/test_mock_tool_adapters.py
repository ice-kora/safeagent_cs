import json
from pathlib import Path

from app.storage.seed_data import seed_sqlite_users_orders
from app.tools.adapter import ToolExecutionContext, ToolRequest
from app.tools.mock_adapters import (
    KnowledgeToolAdapter,
    OrderChangeAddressAdapter,
    OrderQueryAdapter,
    TicketCreateAdapter,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


def test_knowledge_adapter_returns_policy_answer() -> None:
    adapter = KnowledgeToolAdapter()

    result = adapter.execute(
        ToolRequest(
            tool_name=adapter.name,
            tool_args={"query": "七天无理由"},
            context=_context(),
        )
    )

    assert result.success is True
    assert result.data["answer"]
    assert result.data["sources"]


def test_order_query_adapter_returns_sanitized_order_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    seed_sqlite_users_orders(db_path)
    adapter = OrderQueryAdapter()

    result = adapter.execute(
        ToolRequest(
            tool_name=adapter.name,
            tool_args={"order_id": "O10086"},
            context=_context(db_path=db_path),
        )
    )
    result_json = json.dumps(result.to_dict(), ensure_ascii=False)

    assert result.success is True
    assert result.data["order_id"] == "O10086"
    assert "phone" not in result_json
    assert "address" not in result_json
    assert "payment_info" not in result_json


def test_order_change_adapter_requires_idempotency_key(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    seed_sqlite_users_orders(db_path)
    adapter = OrderChangeAddressAdapter()

    result = adapter.execute(
        ToolRequest(
            tool_name=adapter.name,
            tool_args={"order_id": "O10086", "new_address": "敏感详细地址"},
            context=_context(db_path=db_path, idempotency_key=None),
        )
    )

    assert result.success is False
    assert result.error_type == "IDEMPOTENCY_KEY_REQUIRED"


def test_ticket_adapter_creates_ticket_with_idempotency_key(tmp_path: Path) -> None:
    adapter = TicketCreateAdapter()

    result = adapter.execute(
        ToolRequest(
            tool_name=adapter.name,
            tool_args={
                "user_id": "u_1001",
                "action": "request_refund",
                "target_type": "order",
                "target_id": "O10086",
                "ticket_type": "refund",
                "risk_level": "L4",
            },
            context=_context(db_path=tmp_path / "test.db"),
        )
    )

    assert result.success is True
    assert result.data["ticket_id"].startswith("tk_")
    assert result.safe_for_llm is True


def _context(
    db_path: Path | None = None,
    idempotency_key: str | None = "idem_001",
) -> ToolExecutionContext:
    return ToolExecutionContext(
        run_id="run_001",
        session_id="sess_001",
        user_id="u_1001",
        tenant_id="t_001",
        action_plan=None,
        tool_call_id="tc_001",
        idempotency_key=idempotency_key,
        action_fingerprint="af_001",
        metadata={
            "db_path": str(db_path) if db_path else None,
            "mock_dir": str(MOCK_DIR),
        },
    )
