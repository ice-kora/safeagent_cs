from app.tools.adapter import ToolCapability, ToolExecutionContext, ToolRequest
from app.tools.mock_adapters import (
    KnowledgeToolAdapter,
    OrderChangeAddressAdapter,
    OrderQueryAdapter,
    TicketCreateAdapter,
)


def test_tool_execution_context_contains_minimal_fields() -> None:
    context = ToolExecutionContext(
        run_id="run_001",
        session_id="sess_001",
        user_id="u_1001",
        tenant_id="t_001",
        action_plan=None,
        tool_call_id="tc_001",
        idempotency_key="idem_001",
        action_fingerprint="af_001",
    )

    assert context.user_id == "u_1001"
    assert context.idempotency_key == "idem_001"


def test_tool_request_can_be_created() -> None:
    context = ToolExecutionContext(
        run_id=None,
        session_id=None,
        user_id="u_1001",
        tenant_id=None,
        action_plan=None,
        tool_call_id=None,
        idempotency_key=None,
        action_fingerprint=None,
    )

    request = ToolRequest(
        tool_name="knowledge_tool.query_policy",
        tool_args={"query": "发票"},
        context=context,
    )

    assert request.tool_args["query"] == "发票"


def test_tool_capabilities_are_correct() -> None:
    adapters = [
        KnowledgeToolAdapter(),
        OrderQueryAdapter(),
        OrderChangeAddressAdapter(),
        TicketCreateAdapter(),
    ]
    capabilities: dict[str, ToolCapability] = {
        adapter.name: adapter.capability for adapter in adapters
    }

    assert capabilities["knowledge_tool.query_policy"].read_only is True
    assert capabilities["order_tool.query_order"].read_only is True
    assert capabilities["order_tool.change_address"].side_effect is True
    assert capabilities["order_tool.change_address"].requires_idempotency is True
    assert capabilities["ticket_tool.create_ticket"].side_effect is True
    assert capabilities["ticket_tool.create_ticket"].requires_idempotency is True
