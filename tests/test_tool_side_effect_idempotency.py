from app.tools.adapter import ToolExecutionContext, ToolRequest
from app.tools.mock_adapters import (
    KnowledgeToolAdapter,
    OrderChangeAddressAdapter,
    TicketCreateAdapter,
)


def test_read_only_tool_does_not_require_idempotency_key() -> None:
    adapter = KnowledgeToolAdapter()

    result = adapter.execute(
        ToolRequest(
            tool_name=adapter.name,
            tool_args={"query": "退款政策"},
            context=_context(idempotency_key=None),
        )
    )

    assert result.success is True


def test_order_change_side_effect_requires_idempotency_key() -> None:
    adapter = OrderChangeAddressAdapter()

    result = adapter.execute(
        ToolRequest(
            tool_name=adapter.name,
            tool_args={"order_id": "O10086", "new_address": "敏感详细地址"},
            context=_context(idempotency_key=None),
        )
    )

    assert result.success is False
    assert result.error_type == "IDEMPOTENCY_KEY_REQUIRED"


def test_ticket_side_effect_requires_idempotency_key() -> None:
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
            },
            context=_context(idempotency_key=None),
        )
    )

    assert result.success is False
    assert result.error_type == "IDEMPOTENCY_KEY_REQUIRED"


def _context(idempotency_key: str | None) -> ToolExecutionContext:
    return ToolExecutionContext(
        run_id="run_001",
        session_id="sess_001",
        user_id="u_1001",
        tenant_id="t_001",
        action_plan=None,
        tool_call_id="tc_001",
        idempotency_key=idempotency_key,
        action_fingerprint="af_001",
    )
