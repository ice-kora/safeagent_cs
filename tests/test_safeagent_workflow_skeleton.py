import json
from pathlib import Path

from app.core.action_plan import ActionPlan
from app.storage.db import get_connection
from app.workflows.safeagent_nodes import append_node_trace
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


def test_workflow_state_can_be_created() -> None:
    state = SafeAgentWorkflowState(
        request_id="req_test",
        run_id="run_test",
        session_id="sess_001",
        user_id="u_1001",
        tenant_id="t_001",
        message="帮我查一下订单 O10086",
    )

    assert state.request_id == "req_test"
    assert state.run_id == "run_test"
    assert state.trace_events == []
    assert state.errors == []


def test_safe_snapshot_excludes_sensitive_fields() -> None:
    state = SafeAgentWorkflowState(
        request_id="req_test",
        run_id="run_test",
        session_id="sess_001",
        user_id="u_1001",
        message=(
            "手机号 13812345678，详细地址 北京市朝阳区某街道，"
            "api_key=abc123，system prompt 不应外泄"
        ),
    )
    state.action_plan = ActionPlan(
        intent="prompt_injection",
        action="security_risk",
        target_type="security",
        target_id=None,
        tool_name=None,
        tool_args={
            "raw_message": state.message,
            "token": "secret-token",
            "address": "北京市朝阳区某街道",
        },
        reason="安全风险输入。",
    )

    snapshot_text = json.dumps(state.safe_snapshot(), ensure_ascii=False)

    assert "13812345678" not in snapshot_text
    assert "详细地址" not in snapshot_text
    assert "北京市朝阳区某街道" not in snapshot_text
    assert "api_key" not in snapshot_text
    assert "system prompt" not in snapshot_text.lower()
    assert "secret-token" not in snapshot_text


def test_workflow_trace_write_sanitizes_sensitive_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    services = _services(tmp_path)
    run_id = services.trace_service.start_run(
        session_id="sess_001",
        user_id="u_1001",
        request_id="req_trace_sensitive",
    )
    state = SafeAgentWorkflowState(
        request_id="req_trace_sensitive",
        run_id=run_id,
        session_id="sess_001",
        user_id="u_1001",
        message="安全测试",
    )

    append_node_trace(
        state=state,
        services=services,
        node_name="sensitive_trace_test_node",
        event_type="sensitive_trace_test",
        input_json={
            "message": "手机号 13812345678，system prompt，详细地址，api_key=abc123，token=secret-token",
        },
        output_json={
            "summary": "traceback stack trace，详细地址，token=another-secret",
        },
    )

    with get_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT input_json, output_json FROM agent_traces WHERE run_id = ?",
            (run_id,),
        ).fetchall()
    trace_text = json.dumps([dict(row) for row in rows], ensure_ascii=False).lower()

    assert "13812345678" not in trace_text
    assert "api_key" not in trace_text
    assert "token" not in trace_text
    assert "system prompt" not in trace_text
    assert "详细地址" not in trace_text
    assert "traceback" not in trace_text
    assert "secret" not in trace_text


def test_workflow_builder_can_create_runner(tmp_path: Path) -> None:
    workflow = build_safeagent_workflow(_services(tmp_path))

    assert workflow is not None
    assert "intent_node" in workflow.node_names
    assert "planner_node" in workflow.node_names
    assert "finish_node" in workflow.node_names


def test_workflow_node_list_contains_required_nodes(tmp_path: Path) -> None:
    workflow = build_safeagent_workflow(_services(tmp_path))
    required_nodes = {
        "mode_router_node",
        "intent_node",
        "planner_node",
        "llm_output_guard_node",
        "action_plan_validator_node",
        "policy_node",
        "route_by_policy_node",
        "tool_gateway_node",
        "pending_action_node",
        "human_required_node",
        "deny_node",
        "failure_handler_node",
        "response_generation_node",
        "llm_response_guard_node",
        "finish_node",
    }

    assert required_nodes.issubset(set(workflow.node_names))


def test_chat_api_integrates_workflow_only_behind_config_gate() -> None:
    chat_source = (PROJECT_ROOT / "app" / "api" / "chat.py").read_text(
        encoding="utf-8"
    )

    assert "SAFEAGENT_WORKFLOW_MODE" not in chat_source
    assert "WORKFLOW_MODE_WORKFLOW" in chat_source
    assert "handle_workflow_chat" in chat_source
    assert "get_settings().workflow_mode == WORKFLOW_MODE_WORKFLOW" in chat_source


def test_confirm_api_integrates_workflow_only_behind_config_gate() -> None:
    confirm_source = (PROJECT_ROOT / "app" / "api" / "confirm.py").read_text(
        encoding="utf-8"
    )

    assert "WORKFLOW_MODE_WORKFLOW" in confirm_source
    assert "handle_workflow_confirm" in confirm_source
    assert "get_settings().workflow_mode == WORKFLOW_MODE_WORKFLOW" in confirm_source
    assert "build_safeagent_workflow" not in confirm_source
