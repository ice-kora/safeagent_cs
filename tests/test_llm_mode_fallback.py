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
from app.core.config import (
    LLM_MODE_MOCK_LLM,
    LLM_MODE_REAL_LLM,
    LLM_MODE_RULE,
    get_settings,
)
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
from app.core.action_plan_validator import ActionPlanValidator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


def test_llm_mode_defaults_to_rule(monkeypatch) -> None:
    monkeypatch.delenv("SAFEAGENT_LLM_MODE", raising=False)

    assert get_settings().llm_mode == LLM_MODE_RULE


def test_invalid_llm_mode_falls_back_to_rule(monkeypatch) -> None:
    monkeypatch.setenv("SAFEAGENT_LLM_MODE", "invalid")

    assert get_settings().llm_mode == LLM_MODE_RULE


def test_real_llm_mode_is_explicitly_supported(monkeypatch) -> None:
    monkeypatch.setenv("SAFEAGENT_LLM_MODE", LLM_MODE_REAL_LLM)

    assert get_settings().llm_mode == LLM_MODE_REAL_LLM


def test_workflow_mock_llm_mode_falls_back_to_rule_for_policy_query(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    monkeypatch.setenv("SAFEAGENT_LLM_MODE", LLM_MODE_MOCK_LLM)
    client, db_path = _client_with_services(tmp_path)
    try:
        response = _post_chat(client, "你们支持七天无理由退货吗？")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "SUCCESS"
        assert body["intent"] == "policy_query"
        assert body["action"] == "query_policy"
        assert _count_rows(db_path, "tool_call_logs") == 1
    finally:
        app.dependency_overrides.clear()


def test_workflow_mock_llm_mode_falls_back_to_rule_for_order_query(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    monkeypatch.setenv("SAFEAGENT_LLM_MODE", LLM_MODE_MOCK_LLM)
    client, db_path = _client_with_services(tmp_path)
    try:
        response = _post_chat(client, "帮我查一下订单 O10086")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "SUCCESS"
        assert body["intent"] == "order_query"
        assert body["action"] == "query_order"
        assert _count_rows(db_path, "tool_call_logs") == 1
    finally:
        app.dependency_overrides.clear()


def test_manual_mode_ignores_mock_llm_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "manual")
    monkeypatch.setenv("SAFEAGENT_LLM_MODE", LLM_MODE_MOCK_LLM)
    client, db_path = _client_with_services(tmp_path)
    try:
        response = _post_chat(client, "帮我查一下订单 O10086")
        body = response.json()

        assert response.status_code == 200
        assert body["status"] == "SUCCESS"
        assert body["intent"] == "order_query"
        assert _count_rows(db_path, "tool_call_logs") == 1
    finally:
        app.dependency_overrides.clear()


def _client_with_services(tmp_path: Path):
    db_path = tmp_path / "test.db"
    trace_service = TraceService(
        db_path=db_path,
        logging_service=LoggingService(log_path=tmp_path / "application.log"),
    )
    repository = RepositoryService(mock_dir=MOCK_DIR, db_path=db_path)
    app.dependency_overrides[get_trace_service] = lambda: trace_service
    app.dependency_overrides[get_intent_classifier] = lambda: RuleBasedIntentClassifier()
    app.dependency_overrides[get_action_planner] = lambda: RuleBasedActionPlanner()
    app.dependency_overrides[get_action_plan_validator] = lambda: ActionPlanValidator()
    app.dependency_overrides[get_policy_service] = lambda: PolicyService(
        repository=repository
    )
    app.dependency_overrides[get_tool_gateway] = lambda: ToolGateway(
        db_path=db_path,
        mock_dir=MOCK_DIR,
    )
    app.dependency_overrides[get_failure_handler] = lambda: FailureHandler(
        db_path=db_path
    )
    app.dependency_overrides[get_pending_action_service] = (
        lambda: PendingActionService(db_path=db_path)
    )
    return TestClient(app), db_path


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
