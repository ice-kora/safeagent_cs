from pathlib import Path

from app.core.constants import PolicyDecisionType
from app.core.policy import PolicyDecision
from app.core.risk import RiskLevel
from app.storage.db import get_connection
from app.workflows.safeagent_nodes import route_by_policy_node
from app.workflows.safeagent_state import SafeAgentWorkflowState
from app.workflows.safeagent_workflow import build_safeagent_workflow
from app.workflows.service_adapters import SafeAgentWorkflowServices


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


def _services(tmp_path: Path) -> SafeAgentWorkflowServices:
    return SafeAgentWorkflowServices.create_default(
        db_path=tmp_path / "test.db",
        mock_dir=MOCK_DIR,
        log_path=tmp_path / "application.log",
    )


def _count_rows(db_path: Path, table_name: str) -> int:
    with get_connection(db_path) as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]


def _tool_logs(db_path: Path) -> list[dict[str, object]]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT tool_name, attempt_no, status
            FROM tool_call_logs
            ORDER BY created_at ASC, rowid ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _pending_actions(db_path: Path) -> list[dict[str, object]]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT pending_action_id, source_run_id, status
            FROM pending_actions
            ORDER BY created_at ASC, rowid ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _run_workflow(tmp_path: Path, message: str):
    db_path = tmp_path / "test.db"
    services = _services(tmp_path)
    workflow = build_safeagent_workflow(services)
    state = workflow.run(
        session_id="sess_001",
        user_id="u_1001",
        tenant_id="t_001",
        message=message,
    )
    return state, services, db_path


def test_allow_branch_calls_tool_gateway(tmp_path: Path) -> None:
    state, services, db_path = _run_workflow(tmp_path, "帮我查一下订单 O10086")

    assert state.final_status == "SUCCESS"
    assert state.policy_decision.decision == PolicyDecisionType.ALLOW
    assert state.tool_result is not None
    assert state.tool_result.tool_name == "order_tool.query_order"
    assert _tool_logs(db_path)[0]["tool_name"] == "order_tool.query_order"
    assert _count_rows(db_path, "tool_call_logs") == 1
    assert len(services.trace_service.get_traces(state.run_id)) >= 8


def test_deny_branch_does_not_call_tool_gateway(tmp_path: Path) -> None:
    state, _, db_path = _run_workflow(tmp_path, "帮我查一下订单 O10087")

    assert state.final_status == "DENY"
    assert state.policy_decision.decision == PolicyDecisionType.DENY
    assert state.tool_result is None
    assert _count_rows(db_path, "tool_call_logs") == 0
    assert "deny_node" in _trace_node_names(state)


def test_confirm_required_branch_creates_pending_action_without_tool_call(
    tmp_path: Path,
) -> None:
    state, _, db_path = _run_workflow(
        tmp_path,
        "订单 O10086 的地址填错了，帮我改一下",
    )
    pending_actions = _pending_actions(db_path)

    assert state.final_status == "CONFIRM_REQUIRED"
    assert state.pending_action_id is not None
    assert state.pending_action_id.startswith("pa_")
    assert len(pending_actions) == 1
    assert pending_actions[0]["source_run_id"] == state.run_id
    assert pending_actions[0]["status"] == "PENDING"
    assert _count_rows(db_path, "tool_call_logs") == 0
    assert "pending_action_node" in _trace_node_names(state)


def test_human_required_branch_does_not_auto_call_tool(tmp_path: Path) -> None:
    state, _, db_path = _run_workflow(tmp_path, "订单 O10086 我要退款")

    assert state.final_status == "HUMAN_REQUIRED"
    assert state.policy_decision.decision == PolicyDecisionType.HUMAN_REQUIRED
    assert state.tool_result is None
    assert _count_rows(db_path, "tool_call_logs") == 0
    assert "human_required_node" in _trace_node_names(state)


def test_route_by_policy_node_does_not_modify_policy_decision(tmp_path: Path) -> None:
    services = _services(tmp_path)
    run_id = services.trace_service.start_run(
        session_id="sess_001",
        user_id="u_1001",
        request_id="req_route_test",
    )
    state = SafeAgentWorkflowState(
        request_id="req_route_test",
        run_id=run_id,
        session_id="sess_001",
        user_id="u_1001",
        message="测试路由",
    )
    policy_decision = PolicyDecision(
        decision=PolicyDecisionType.ALLOW,
        risk_level=RiskLevel.L2,
        reason="unit test",
    )
    state.policy_decision = policy_decision
    before = policy_decision.to_dict()

    route = route_by_policy_node(state, services)

    assert route == "ALLOW"
    assert state.policy_decision is policy_decision
    assert state.policy_decision.to_dict() == before


def test_workflow_run_records_key_trace_events(tmp_path: Path) -> None:
    state, _, _ = _run_workflow(tmp_path, "你们支持七天无理由退货吗？")
    event_types = {event["event_type"] for event in state.trace_events}

    assert {
        "workflow_started",
        "intent_classified",
        "plan_generated",
        "action_plan_validated",
        "policy_decided",
        "route_selected",
        "tool_called",
        "failure_handled",
        "response_generated",
        "workflow_finished",
    }.issubset(event_types)


def _trace_node_names(state) -> set[str]:
    return {event["node_name"] for event in state.trace_events}

