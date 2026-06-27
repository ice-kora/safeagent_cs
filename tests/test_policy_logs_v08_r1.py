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
from app.api.observability import get_observability_runtime_store
from app.core.action_plan_validator import ActionPlanValidator
from app.main import app
from app.services.failure_handler import FailureHandler
from app.services.intent_service import RuleBasedIntentClassifier
from app.services.pending_action_service import PendingActionService
from app.services.planner_service import RuleBasedActionPlanner
from app.services.policy_service import PolicyService
from app.services.repository_service import RepositoryService
from app.services.tool_gateway import ToolGateway
from app.services.trace_service import TraceService
from app.storage.runtime_store import get_runtime_store


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


def test_chat_policy_decision_is_visible_through_observability(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "manual")
    monkeypatch.setenv("SAFEAGENT_RUNTIME_BACKEND", "sqlite")
    db_path = tmp_path / "runtime.db"
    trace_service = TraceService(db_path=db_path)
    repository = RepositoryService(mock_dir=MOCK_DIR, db_path=db_path)
    policy_service = PolicyService(repository=repository)
    runtime_store = get_runtime_store(db_path=db_path)

    app.dependency_overrides.clear()
    app.dependency_overrides[get_trace_service] = lambda: trace_service
    app.dependency_overrides[get_intent_classifier] = lambda: RuleBasedIntentClassifier()
    app.dependency_overrides[get_action_planner] = lambda: RuleBasedActionPlanner()
    app.dependency_overrides[get_action_plan_validator] = lambda: ActionPlanValidator()
    app.dependency_overrides[get_policy_service] = lambda: policy_service
    app.dependency_overrides[get_tool_gateway] = lambda: ToolGateway(
        db_path=db_path,
        mock_dir=MOCK_DIR,
    )
    app.dependency_overrides[get_failure_handler] = lambda: FailureHandler(
        db_path=db_path
    )
    app.dependency_overrides[get_pending_action_service] = lambda: PendingActionService(
        db_path=db_path
    )
    app.dependency_overrides[get_observability_runtime_store] = lambda: runtime_store

    try:
        client = TestClient(app)
        response = client.post(
            "/api/chat",
            json={
                "session_id": "sess_policy_log_v08_r1",
                "user_id": "u_1001",
                "message": "你们支持七天无理由退货吗？",
            },
        )
        body = response.json()
        logs_response = client.get(f"/api/runs/{body['run_id']}/policy-logs")
        policy_logs = logs_response.json()
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert logs_response.status_code == 200
    assert len(policy_logs) == 1
    assert policy_logs[0]["run_id"] == body["run_id"]
    assert policy_logs[0]["request_id"] == body["request_id"]
    assert policy_logs[0]["session_id"] == "sess_policy_log_v08_r1"
    assert policy_logs[0]["user_id"] == "u_1001"
    assert policy_logs[0]["action"] == "query_policy"
    assert policy_logs[0]["tool_name"] == "knowledge_tool.query_policy"
    assert policy_logs[0]["decision"] == "ALLOW"
    assert policy_logs[0]["risk_level"] == body["policy_decision"]["risk_level"]
    assert policy_logs[0]["reason"]
    assert policy_logs[0]["code"] == "ALLOW"
    assert policy_logs[0]["created_at"]
