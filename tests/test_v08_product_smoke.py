from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.chat import (
    get_action_plan_validator,
    get_action_planner,
    get_failure_handler,
    get_intent_classifier,
    get_pending_action_service as get_chat_pending_action_service,
    get_policy_service as get_chat_policy_service,
    get_tool_gateway as get_chat_tool_gateway,
    get_trace_service as get_chat_trace_service,
)
from app.api.confirm import (
    get_pending_action_service as get_confirm_pending_action_service,
    get_policy_service as get_confirm_policy_service,
    get_tool_gateway as get_confirm_tool_gateway,
    get_trace_service as get_confirm_trace_service,
)
from app.api.observability import get_observability_runtime_store
from app.core.action_plan_validator import ActionPlanValidator
from app.core.config import (
    WORKFLOW_ENGINE_LANGGRAPH,
    WORKFLOW_MODE_WORKFLOW,
    get_settings,
)
from app.main import app
from app.services.failure_handler import FailureHandler
from app.services.intent_service import RuleBasedIntentClassifier
from app.services.pending_action_service import PendingActionService
from app.services.planner_service import RuleBasedActionPlanner
from app.services.policy_service import PolicyService
from app.services.repository_service import RepositoryService
from app.services.tool_gateway import ToolGateway
from app.services.trace_service import TraceService
from app.storage.database_config import DB_BACKEND_POSTGRES, DB_BACKEND_SQLITE
from app.storage.runtime_config import RUNTIME_BACKEND_POSTGRES
from app.storage.runtime_store import get_runtime_store


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_demo_profile_langgraph_chat_confirm_and_observability_smoke(
    tmp_path: Path,
    monkeypatch,
) -> None:
    for key in (
        "SAFEAGENT_WORKFLOW_MODE",
        "SAFEAGENT_WORKFLOW_ENGINE",
        "SAFEAGENT_LLM_MODE",
        "SAFEAGENT_DB_BACKEND",
        "SAFEAGENT_RUNTIME_BACKEND",
        "SAFEAGENT_TOOL_BACKEND",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SAFEAGENT_PROFILE", "demo")

    settings = get_settings()
    assert settings.workflow_mode == WORKFLOW_MODE_WORKFLOW
    assert settings.workflow_engine == WORKFLOW_ENGINE_LANGGRAPH
    assert settings.db_backend == DB_BACKEND_POSTGRES
    assert settings.runtime_backend == RUNTIME_BACKEND_POSTGRES

    db_path = tmp_path / "runtime.db"
    trace_service = TraceService(db_path=db_path)
    repository = RepositoryService(
        mock_dir=MOCK_DIR,
        db_path=db_path,
        db_backend=DB_BACKEND_SQLITE,
    )
    policy_service = PolicyService(repository=repository)
    tool_gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)
    pending_action_service = PendingActionService(db_path=db_path)
    failure_handler = FailureHandler(db_path=db_path)
    runtime_store = get_runtime_store(db_path=db_path)

    app.dependency_overrides[get_chat_trace_service] = lambda: trace_service
    app.dependency_overrides[get_intent_classifier] = lambda: RuleBasedIntentClassifier()
    app.dependency_overrides[get_action_planner] = lambda: RuleBasedActionPlanner()
    app.dependency_overrides[get_action_plan_validator] = lambda: ActionPlanValidator()
    app.dependency_overrides[get_chat_policy_service] = lambda: policy_service
    app.dependency_overrides[get_chat_tool_gateway] = lambda: tool_gateway
    app.dependency_overrides[get_failure_handler] = lambda: failure_handler
    app.dependency_overrides[get_chat_pending_action_service] = (
        lambda: pending_action_service
    )
    app.dependency_overrides[get_confirm_pending_action_service] = (
        lambda: pending_action_service
    )
    app.dependency_overrides[get_confirm_trace_service] = lambda: trace_service
    app.dependency_overrides[get_confirm_policy_service] = lambda: policy_service
    app.dependency_overrides[get_confirm_tool_gateway] = lambda: tool_gateway
    app.dependency_overrides[get_observability_runtime_store] = lambda: runtime_store

    client = TestClient(app)

    chat_response = client.post(
        "/api/chat",
        json={
            "session_id": "sess_v08_demo",
            "user_id": "u_1001",
            "message": "订单 O10086 的地址填错了，帮我改一下",
        },
    )
    chat_body = chat_response.json()

    assert chat_response.status_code == 200
    assert chat_body["status"] == "CONFIRM_REQUIRED"
    assert chat_body["pending_action_id"].startswith("pa_")

    trace_response = client.get(f"/api/runs/{chat_body['run_id']}/traces")
    traces = trace_response.json()
    policy_logs = client.get(f"/api/runs/{chat_body['run_id']}/policy-logs").json()
    assert trace_response.status_code == 200
    assert traces[0]["node_name"] == "workflow_start_node"
    assert any(trace["node_name"] == "pending_action_node" for trace in traces)
    assert policy_logs[0]["request_id"] == chat_body["request_id"]
    assert policy_logs[0]["action"] == "change_address"
    assert policy_logs[0]["tool_name"] == "order_tool.change_address"
    assert policy_logs[0]["decision"] == "CONFIRM_REQUIRED"

    confirm_response = client.post(
        "/api/confirm",
        json={
            "pending_action_id": chat_body["pending_action_id"],
            "user_id": "u_1001",
            "session_id": "sess_v08_demo",
            "confirm": False,
        },
    )
    confirm_body = confirm_response.json()

    assert confirm_response.status_code == 200
    assert confirm_body["status"] == "CANCELLED"
    confirm_traces = client.get(f"/api/runs/{confirm_body['run_id']}/traces").json()
    assert any(trace["node_name"] == "confirm_cancel_node" for trace in confirm_traces)
