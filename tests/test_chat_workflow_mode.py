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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


class SpyIntentClassifier(RuleBasedIntentClassifier):
    def __init__(self) -> None:
        self.calls = 0

    def classify(self, message: str) -> str:
        self.calls += 1
        return super().classify(message)


class AlwaysInvalidValidator:
    def validate(self, action_plan):
        return ValidationResult(
            ValidationStatus.PLAN_INVALID,
            "unit test invalid plan",
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


def _client_with_services(
    tmp_path: Path,
    intent_classifier=None,
    validator=None,
    tool_gateway=None,
):
    db_path = tmp_path / "test.db"
    trace_service = TraceService(
        db_path=db_path,
        logging_service=LoggingService(log_path=tmp_path / "application.log"),
    )
    repository = RepositoryService(mock_dir=MOCK_DIR, db_path=db_path)
    policy_service = PolicyService(repository=repository)
    selected_tool_gateway = tool_gateway or ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)
    pending_action_service = PendingActionService(db_path=db_path)

    selected_intent_classifier = intent_classifier or RuleBasedIntentClassifier()
    app.dependency_overrides[get_trace_service] = lambda: trace_service
    app.dependency_overrides[get_intent_classifier] = lambda: selected_intent_classifier
    app.dependency_overrides[get_action_planner] = lambda: RuleBasedActionPlanner()
    app.dependency_overrides[get_action_plan_validator] = (
        lambda: validator or ActionPlanValidator()
    )
    app.dependency_overrides[get_policy_service] = lambda: policy_service
    app.dependency_overrides[get_tool_gateway] = lambda: selected_tool_gateway
    app.dependency_overrides[get_failure_handler] = lambda: FailureHandler(db_path=db_path)
    app.dependency_overrides[get_pending_action_service] = lambda: pending_action_service
    return TestClient(app), trace_service, pending_action_service, db_path


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


def _post_chat(client: TestClient, message: str):
    return client.post(
        "/api/chat",
        json={
            "session_id": "sess_001",
            "user_id": "u_1001",
            "message": message,
        },
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


def _run_status(db_path: Path, run_id: str) -> str:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT status FROM agent_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    return row["status"]


def _trace_node_names(trace_service: TraceService, run_id: str) -> list[str]:
    return [trace["node_name"] for trace in trace_service.get_traces(run_id)]


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


def test_chat_defaults_to_manual_when_workflow_mode_unset(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("SAFEAGENT_WORKFLOW_MODE", raising=False)
    client, trace_service, _, _ = _client_with_services(tmp_path)
    try:
        response = _post_chat(client, "你们支持七天无理由退货吗？")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "SUCCESS"
        assert "intent_classification" in _trace_node_names(trace_service, body["run_id"])
        assert "workflow_start_node" not in _trace_node_names(trace_service, body["run_id"])
    finally:
        _clear_overrides()


def test_chat_manual_mode_keeps_manual_flow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "manual")
    client, trace_service, _, _ = _client_with_services(tmp_path)
    try:
        response = _post_chat(client, "帮我查一下订单 O10086")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "SUCCESS"
        assert "intent_classification" in _trace_node_names(trace_service, body["run_id"])
        assert "intent_node" not in _trace_node_names(trace_service, body["run_id"])
    finally:
        _clear_overrides()


def test_chat_invalid_workflow_mode_falls_back_to_manual(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "invalid")
    client, trace_service, _, _ = _client_with_services(tmp_path)
    try:
        response = _post_chat(client, "你们支持开发票吗？")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "SUCCESS"
        assert "intent_classification" in _trace_node_names(trace_service, body["run_id"])
        assert "workflow_start_node" not in _trace_node_names(trace_service, body["run_id"])
    finally:
        _clear_overrides()


def test_chat_workflow_mode_uses_workflow_adapter(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    spy_intent = SpyIntentClassifier()
    client, trace_service, _, _ = _client_with_services(
        tmp_path,
        intent_classifier=spy_intent,
    )
    try:
        response = _post_chat(client, "你们支持七天无理由退货吗？")
        body = response.json()
        trace_nodes = _trace_node_names(trace_service, body["run_id"])

        assert response.status_code == 200
        assert body["status"] == "SUCCESS"
        assert spy_intent.calls == 1
        assert "workflow_start_node" in trace_nodes
        assert "intent_node" in trace_nodes
        assert "intent_classification" not in trace_nodes
    finally:
        _clear_overrides()


def test_chat_workflow_mode_allow_writes_tool_call_logs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    client, _, _, db_path = _client_with_services(tmp_path)
    try:
        response = _post_chat(client, "帮我查一下订单 O10086")
        body = response.json()
        tool_logs = _tool_logs(db_path)

        assert response.status_code == 200
        assert body["status"] == "SUCCESS"
        assert body["tool_result"]["tool_name"] == "order_tool.query_order"
        assert len(tool_logs) == 1
        assert tool_logs[0]["tool_name"] == "order_tool.query_order"
    finally:
        _clear_overrides()


def test_chat_workflow_mode_deny_skips_tool_gateway(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    client, _, _, db_path = _client_with_services(tmp_path)
    try:
        response = _post_chat(client, "帮我查一下订单 O10087")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "DENY"
        assert _count_rows(db_path, "tool_call_logs") == 0
    finally:
        _clear_overrides()


def test_chat_workflow_mode_confirm_required_creates_pending_action_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    client, _, pending_action_service, db_path = _client_with_services(tmp_path)
    try:
        response = _post_chat(client, "订单 O10086 的地址填错了，帮我改一下")
        body = response.json()
        pending_action = pending_action_service.get_pending_action(
            body["pending_action_id"]
        )

        assert response.status_code == 200
        assert body["status"] == "CONFIRM_REQUIRED"
        assert body["pending_action_id"].startswith("pa_")
        assert pending_action["status"] == "PENDING"
        assert _count_rows(db_path, "pending_actions") == 1
        assert _count_rows(db_path, "tool_call_logs") == 0
    finally:
        _clear_overrides()


def test_chat_workflow_mode_human_required_does_not_auto_call_tool(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    client, trace_service, _, db_path = _client_with_services(tmp_path)
    try:
        response = _post_chat(client, "订单 O10086 我要退款")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "HUMAN_REQUIRED"
        assert "human_required_node" in _trace_node_names(trace_service, body["run_id"])
        assert _count_rows(db_path, "tool_call_logs") == 0
    finally:
        _clear_overrides()


def test_chat_workflow_mode_plan_invalid_skips_tool_gateway(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    client, trace_service, _, db_path = _client_with_services(
        tmp_path,
        validator=AlwaysInvalidValidator(),
    )
    try:
        response = _post_chat(client, "帮我查一下订单 O10086")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "PLAN_INVALID"
        assert body["validation_result"]["status"] == "PLAN_INVALID"
        assert "policy_node" not in _trace_node_names(trace_service, body["run_id"])
        assert _count_rows(db_path, "tool_call_logs") == 0
    finally:
        _clear_overrides()


def test_chat_workflow_mode_tool_failed_uses_failure_handler(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    db_path = tmp_path / "test.db"
    fake_gateway = SequenceToolGateway(
        db_path=db_path,
        results=[
            _retryable_failure("knowledge_tool.query_policy"),
            _retryable_failure("knowledge_tool.query_policy"),
        ],
    )
    client, trace_service, _, _ = _client_with_services(
        tmp_path,
        tool_gateway=fake_gateway,
    )
    try:
        response = _post_chat(client, "你们支持七天无理由退货吗？")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "TOOL_FAILED"
        assert body["failure_result"]["status"] == "FAILED"
        assert [call["attempt_no"] for call in fake_gateway.calls] == [1, 2]
        assert "failure_handler_node" in _trace_node_names(trace_service, body["run_id"])
        assert _run_status(db_path, body["run_id"]) == "FAILED"
    finally:
        _clear_overrides()


def test_confirm_api_integrates_workflow_only_behind_config_gate() -> None:
    confirm_source = (PROJECT_ROOT / "app" / "api" / "confirm.py").read_text(
        encoding="utf-8"
    )

    assert "WORKFLOW_MODE_WORKFLOW" in confirm_source
    assert "handle_workflow_confirm" in confirm_source
    assert "get_settings().workflow_mode == WORKFLOW_MODE_WORKFLOW" in confirm_source
    assert "build_safeagent_workflow" not in confirm_source
