from pathlib import Path

from fastapi.testclient import TestClient

from app.api.chat import (
    get_action_plan_validator,
    get_action_planner,
    get_failure_handler,
    get_intent_classifier,
    get_pending_action_service,
    get_policy_service,
    get_tool_gateway,
    get_trace_service,
)
from app.core.action_plan_validator import (
    ActionPlanValidator,
    ValidationResult,
    ValidationStatus,
)
from app.core.config import (
    WORKFLOW_ENGINE_STYLE,
    WORKFLOW_MODE_MANUAL,
    get_settings,
)
from app.core.tool_result import ToolError, ToolResult
from app.main import app
from app.services.failure_handler import FailureHandler
from app.services.intent_service import RuleBasedIntentClassifier
from app.services.logging_service import LoggingService
from app.services.pending_action_service import PendingActionService
from app.services.planner_service import RuleBasedActionPlanner
from app.services.policy_service import PolicyService
from app.services.repository_service import RepositoryService
from app.services.tool_gateway import ToolGateway
from app.services.trace_service import TraceService
from app.storage.db import get_connection
from app.workflows.langgraph_chat_workflow import (
    build_langgraph_chat_workflow,
    run_langgraph_chat_workflow,
)
from app.workflows.service_adapters import SafeAgentWorkflowServices


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


class AlwaysInvalidValidator:
    def validate(self, action_plan):
        return ValidationResult(
            ValidationStatus.PLAN_INVALID,
            "langgraph unit test invalid plan",
        )


class SequenceToolGateway(ToolGateway):
    def __init__(self, db_path: Path, results: list[ToolResult]) -> None:
        super().__init__(db_path=db_path, mock_dir=MOCK_DIR)
        self.results = results
        self.calls: list[dict[str, object]] = []

    def call_tool(
        self,
        run_id: str,
        session_id: str,
        tool_name: str,
        tool_args: dict | None = None,
        attempt_no: int = 1,
    ) -> ToolResult:
        self.calls.append(
            {
                "run_id": run_id,
                "session_id": session_id,
                "tool_name": tool_name,
                "tool_args": tool_args or {},
                "attempt_no": attempt_no,
            }
        )
        result_index = min(len(self.calls) - 1, len(self.results) - 1)
        result = self.results[result_index]
        self._write_tool_call_log(
            run_id=run_id,
            session_id=session_id,
            tool_name=tool_name,
            tool_args=tool_args or {},
            result=result,
            attempt_no=attempt_no,
            latency_ms=0,
        )
        return result


def test_langgraph_chat_workflow_can_be_built(tmp_path: Path) -> None:
    workflow = build_langgraph_chat_workflow(_services(tmp_path))

    assert workflow is not None
    assert workflow.__class__.__name__ == "CompiledStateGraph"


def test_workflow_engine_defaults_to_style(monkeypatch) -> None:
    monkeypatch.delenv("SAFEAGENT_WORKFLOW_ENGINE", raising=False)

    assert get_settings().workflow_engine == WORKFLOW_ENGINE_STYLE


def test_invalid_workflow_engine_falls_back_to_style(monkeypatch) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_ENGINE", "invalid")

    assert get_settings().workflow_engine == WORKFLOW_ENGINE_STYLE


def test_manual_mode_does_not_use_langgraph_engine(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", WORKFLOW_MODE_MANUAL)
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_ENGINE", "langgraph")
    client, trace_service, _, _ = _client_with_services(tmp_path)
    try:
        response = _post_chat(client, "你们支持七天无理由退货吗？")
        body = response.json()
        trace_nodes = _trace_node_names(trace_service, body["run_id"])

        assert response.status_code == 200
        assert body["status"] == "SUCCESS"
        assert "intent_classification" in trace_nodes
        assert "workflow_start_node" not in trace_nodes
        assert "llm_response_guard_node" not in trace_nodes
    finally:
        app.dependency_overrides.clear()


def test_workflow_mode_style_uses_existing_style_engine(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_ENGINE", "style")
    client, trace_service, _, _ = _client_with_services(tmp_path)
    try:
        response = _post_chat(client, "你们支持七天无理由退货吗？")
        body = response.json()
        trace_nodes = _trace_node_names(trace_service, body["run_id"])

        assert response.status_code == 200
        assert body["status"] == "SUCCESS"
        assert "workflow_start_node" in trace_nodes
        assert "llm_response_guard_node" not in trace_nodes
    finally:
        app.dependency_overrides.clear()


def test_workflow_mode_langgraph_uses_real_langgraph_engine(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_ENGINE", "langgraph")
    client, trace_service, _, _ = _client_with_services(tmp_path)
    try:
        response = _post_chat(client, "你们支持七天无理由退货吗？")
        body = response.json()
        trace_nodes = _trace_node_names(trace_service, body["run_id"])

        assert response.status_code == 200
        assert body["status"] == "SUCCESS"
        assert "workflow_start_node" in trace_nodes
        assert "llm_output_guard_node" in trace_nodes
        assert "llm_response_guard_node" in trace_nodes
    finally:
        app.dependency_overrides.clear()


def test_langgraph_policy_query_allow_success(tmp_path: Path) -> None:
    state, db_path = _run_langgraph(tmp_path, "你们支持七天无理由退货吗？")

    assert state.final_status == "SUCCESS"
    assert state.tool_result.tool_name == "knowledge_tool.query_policy"
    assert _tool_logs(db_path) == ["knowledge_tool.query_policy"]


def test_langgraph_order_query_allow_success(tmp_path: Path) -> None:
    state, db_path = _run_langgraph(tmp_path, "帮我查一下订单 O10086")

    assert state.final_status == "SUCCESS"
    assert state.tool_result.tool_name == "order_tool.query_order"
    assert _tool_logs(db_path) == ["order_tool.query_order"]


def test_langgraph_deny_does_not_call_tool(tmp_path: Path) -> None:
    state, db_path = _run_langgraph(tmp_path, "帮我查一下订单 O10087")

    assert state.final_status == "DENY"
    assert state.tool_result is None
    assert _count_rows(db_path, "tool_call_logs") == 0
    assert "deny_node" in _state_trace_nodes(state)


def test_langgraph_confirm_required_creates_pending_action_without_tool(
    tmp_path: Path,
) -> None:
    state, db_path = _run_langgraph(
        tmp_path,
        "订单 O10086 的地址填错了，帮我改一下",
    )

    assert state.final_status == "CONFIRM_REQUIRED"
    assert state.pending_action_id.startswith("pa_")
    assert _count_rows(db_path, "pending_actions") == 1
    assert _count_rows(db_path, "tool_call_logs") == 0
    assert "pending_action_node" in _state_trace_nodes(state)


def test_langgraph_human_required_does_not_call_tool(tmp_path: Path) -> None:
    state, db_path = _run_langgraph(tmp_path, "订单 O10086 我要退款")

    assert state.final_status == "HUMAN_REQUIRED"
    assert state.tool_result is None
    assert _count_rows(db_path, "tool_call_logs") == 0
    assert "human_required_node" in _state_trace_nodes(state)


def test_langgraph_plan_invalid_skips_policy_and_tool(tmp_path: Path) -> None:
    services = _services(tmp_path, validator=AlwaysInvalidValidator())
    state = run_langgraph_chat_workflow(
        session_id="sess_001",
        user_id="u_1001",
        message="帮我查一下订单 O10086",
        services=services,
    )
    db_path = tmp_path / "test.db"

    assert state.final_status == "PLAN_INVALID"
    assert "policy_node" not in _state_trace_nodes(state)
    assert _count_rows(db_path, "tool_call_logs") == 0


def test_langgraph_tool_failed_enters_failure_handler(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    fake_gateway = SequenceToolGateway(
        db_path=db_path,
        results=[
            _retryable_failure("knowledge_tool.query_policy"),
            _retryable_failure("knowledge_tool.query_policy"),
        ],
    )
    services = _services(tmp_path, tool_gateway=fake_gateway)
    state = run_langgraph_chat_workflow(
        session_id="sess_001",
        user_id="u_1001",
        message="你们支持七天无理由退货吗？",
        services=services,
    )

    assert state.final_status == "TOOL_FAILED"
    assert state.failure_result.status.value == "FAILED"
    assert [call["attempt_no"] for call in fake_gateway.calls] == [1, 2]
    assert "failure_handler_node" in _state_trace_nodes(state)
    assert _run_status(db_path, state.run_id) == "FAILED"


def test_langgraph_response_shape_is_compatible_with_style_workflow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    style_body = _post_chat_with_engine(tmp_path / "style", monkeypatch, "style")
    langgraph_body = _post_chat_with_engine(
        tmp_path / "langgraph",
        monkeypatch,
        "langgraph",
    )

    assert set(style_body.keys()) == set(langgraph_body.keys())
    assert style_body["status"] == langgraph_body["status"] == "SUCCESS"
    assert style_body["tool_result"]["tool_name"] == (
        langgraph_body["tool_result"]["tool_name"]
    )


def test_style_vs_langgraph_chat_branches_match(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cases = [
        ("policy_query", "你们支持七天无理由退货吗？", "SUCCESS"),
        ("order_query_allow", "帮我查一下订单 O10086", "SUCCESS"),
        ("order_query_deny", "帮我查一下订单 O10087", "DENY"),
        ("address_change", "订单 O10086 的地址填错了，帮我改一下", "CONFIRM_REQUIRED"),
        ("refund_request", "订单 O10086 我要退款", "HUMAN_REQUIRED"),
    ]

    for case_id, message, expected_status in cases:
        style_body = _post_chat_with_engine(
            tmp_path / f"{case_id}_style",
            monkeypatch,
            "style",
            message=message,
        )
        langgraph_body = _post_chat_with_engine(
            tmp_path / f"{case_id}_langgraph",
            monkeypatch,
            "langgraph",
            message=message,
        )

        assert style_body["status"] == expected_status
        assert langgraph_body["status"] == expected_status
        assert style_body["action"] == langgraph_body["action"]


def test_style_vs_langgraph_invalid_plan_match(
    tmp_path: Path,
    monkeypatch,
) -> None:
    style_body = _post_chat_with_engine(
        tmp_path / "invalid_style",
        monkeypatch,
        "style",
        validator=AlwaysInvalidValidator(),
    )
    langgraph_body = _post_chat_with_engine(
        tmp_path / "invalid_langgraph",
        monkeypatch,
        "langgraph",
        validator=AlwaysInvalidValidator(),
    )

    assert style_body["status"] == "PLAN_INVALID"
    assert langgraph_body["status"] == "PLAN_INVALID"
    assert style_body["action"] == langgraph_body["action"]


def _services(
    tmp_path: Path,
    validator=None,
    tool_gateway=None,
) -> SafeAgentWorkflowServices:
    db_path = tmp_path / "test.db"
    trace_service = TraceService(
        db_path=db_path,
        logging_service=LoggingService(log_path=tmp_path / "application.log"),
    )
    repository = RepositoryService(mock_dir=MOCK_DIR, db_path=db_path)
    return SafeAgentWorkflowServices(
        trace_service=trace_service,
        intent_classifier=RuleBasedIntentClassifier(),
        action_planner=RuleBasedActionPlanner(),
        action_plan_validator=validator or ActionPlanValidator(),
        policy_service=PolicyService(repository=repository),
        tool_gateway=tool_gateway or ToolGateway(db_path=db_path, mock_dir=MOCK_DIR),
        failure_handler=FailureHandler(db_path=db_path),
        pending_action_service=PendingActionService(db_path=db_path),
    )


def _client_with_services(
    tmp_path: Path,
    validator=None,
    tool_gateway=None,
):
    services = _services(
        tmp_path,
        validator=validator,
        tool_gateway=tool_gateway,
    )
    app.dependency_overrides[get_trace_service] = lambda: services.trace_service
    app.dependency_overrides[get_intent_classifier] = (
        lambda: services.intent_classifier
    )
    app.dependency_overrides[get_action_planner] = lambda: services.action_planner
    app.dependency_overrides[get_action_plan_validator] = (
        lambda: services.action_plan_validator
    )
    app.dependency_overrides[get_policy_service] = lambda: services.policy_service
    app.dependency_overrides[get_tool_gateway] = lambda: services.tool_gateway
    app.dependency_overrides[get_failure_handler] = lambda: services.failure_handler
    app.dependency_overrides[get_pending_action_service] = (
        lambda: services.pending_action_service
    )
    return TestClient(app), services.trace_service, services.pending_action_service, tmp_path / "test.db"


def _run_langgraph(tmp_path: Path, message: str):
    services = _services(tmp_path)
    state = run_langgraph_chat_workflow(
        session_id="sess_001",
        user_id="u_1001",
        message=message,
        services=services,
    )
    return state, tmp_path / "test.db"


def _post_chat(client: TestClient, message: str):
    return client.post(
        "/api/chat",
        json={
            "session_id": "sess_001",
            "user_id": "u_1001",
            "message": message,
        },
    )


def _post_chat_with_engine(
    tmp_path: Path,
    monkeypatch,
    engine: str,
    message: str = "你们支持七天无理由退货吗？",
    validator=None,
) -> dict:
    tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_ENGINE", engine)
    client, _, _, _ = _client_with_services(tmp_path, validator=validator)
    try:
        response = _post_chat(client, message)
        assert response.status_code == 200
        return response.json()
    finally:
        app.dependency_overrides.clear()


def _count_rows(db_path: Path, table_name: str) -> int:
    with get_connection(db_path) as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]


def _tool_logs(db_path: Path) -> list[str]:
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT tool_name
            FROM tool_call_logs
            ORDER BY created_at ASC, rowid ASC
            """
        ).fetchall()
    return [row["tool_name"] for row in rows]


def _run_status(db_path: Path, run_id: str) -> str:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT status FROM agent_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    return row["status"]


def _trace_node_names(trace_service: TraceService, run_id: str) -> set[str]:
    return {trace["node_name"] for trace in trace_service.get_traces(run_id)}


def _state_trace_nodes(state) -> set[str]:
    return {event["node_name"] for event in state.trace_events}


def _retryable_failure(tool_name: str) -> ToolResult:
    return ToolResult(
        success=False,
        tool_name=tool_name,
        data={},
        summary="工具调用超时。",
        error_type="TOOL_TIMEOUT",
        safe_for_llm=True,
        error=ToolError(
            failure_type="TOOL_TIMEOUT",
            message="unit test timeout",
            retryable=True,
        ),
    )
