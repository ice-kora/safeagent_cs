import inspect
from pathlib import Path

from app.core.action_plan import ActionPlan
from app.core.action_plan_validator import ActionPlanValidator
from app.services.tool_gateway import ToolGateway
from app.tools.registry import ToolAdapterRegistry
from app.tools.mcp_adapter import MCPToolAdapter


def test_mcp_mock_tool_executes_only_through_tool_gateway(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_MCP_MOCK_ENABLED", "true")
    gateway = ToolGateway(
        db_path=tmp_path / "runtime.db",
        adapter_registry=ToolAdapterRegistry([MCPToolAdapter()]),
    )

    result = gateway.call_tool(
        run_id="run_mcp",
        session_id="sess_mcp",
        tool_name="mcp.mock.echo",
        tool_args={"message": "hello", "token": "secret-token"},
    )

    assert result.success is True
    assert result.tool_name == "mcp.mock.echo"
    assert result.data["transport"] == "mock"
    assert result.data["arguments_echo"]["token"] == "***"


def test_unallowlisted_mcp_tool_is_rejected_before_adapter(tmp_path: Path) -> None:
    gateway = ToolGateway(db_path=tmp_path / "runtime.db")

    result = gateway.call_tool(
        run_id="run_mcp",
        session_id="sess_mcp",
        tool_name="mcp.not_allowlisted",
        tool_args={},
    )

    assert result.success is False
    assert result.error_type == "TOOL_NOT_IN_ALLOWLIST"


def test_llm_candidate_cannot_select_mcp_tool_via_action_plan_validator() -> None:
    result = ActionPlanValidator().validate(
        ActionPlan(
            intent="order_query",
            action="query_order",
            target_type="order",
            target_id="O10086",
            tool_name="mcp.mock.echo",
            tool_args={"order_id": "O10086"},
        )
    )

    assert result.is_valid is False


def test_mcp_adapter_does_not_call_policy_or_tool_gateway() -> None:
    source = inspect.getsource(MCPToolAdapter)

    assert "PolicyService" not in source
    assert "from app.services.tool_gateway" not in source
    assert "ToolGateway(" not in source
