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
from app.api.checkpoints import get_checkpoint_service, get_resume_service
from app.api.confirm import (
    get_pending_action_service as get_confirm_pending_action_service,
    get_policy_service as get_confirm_policy_service,
    get_tool_gateway as get_confirm_tool_gateway,
    get_trace_service as get_confirm_trace_service,
)
from app.api.observability import get_observability_runtime_store
from app.core.action_plan_validator import ActionPlanValidator
from app.main import app
from app.services.checkpoint_service import CheckpointService
from app.services.failure_handler import FailureHandler
from app.services.intent_service import RuleBasedIntentClassifier
from app.services.pending_action_service import PendingActionService
from app.services.planner_service import RuleBasedActionPlanner
from app.services.policy_service import PolicyService
from app.services.repository_service import RepositoryService
from app.services.resume_service import ResumeService
from app.services.tool_gateway import ToolGateway
from app.services.trace_service import TraceService
from app.storage.db import get_connection
from app.storage.runtime_store import get_runtime_store


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


@pytest.fixture(autouse=True)
def clear_dependency_overrides(monkeypatch):
    app.dependency_overrides.clear()
    monkeypatch.setenv("SAFEAGENT_PROFILE", "dev")
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "manual")
    monkeypatch.setenv("SAFEAGENT_RUNTIME_BACKEND", "sqlite")
    yield
    app.dependency_overrides.clear()


def test_chat_creates_checkpoint_and_resume_rechecks_policy_without_tool(
    tmp_path: Path,
) -> None:
    client, db_path = _client(tmp_path)

    chat = client.post(
        "/api/chat",
        json={
            "session_id": "sess_resume",
            "user_id": "u_1001",
            "message": "订单 O10086 的地址填错了，帮我改一下",
        },
    )
    body = chat.json()

    assert chat.status_code == 200
    assert body["status"] == "CONFIRM_REQUIRED"
    assert body["pending_action_id"].startswith("pa_")
    assert body["checkpoint_id"].startswith("cp_")

    checkpoints = client.get(
        "/api/checkpoints",
        params={"user_id": "u_1001", "session_id": "sess_resume"},
    ).json()
    assert checkpoints[0]["checkpoint_id"] == body["checkpoint_id"]
    assert checkpoints[0]["status"] == "WAITING_CONFIRMATION"

    resume = client.post(
        f"/api/checkpoints/{body['checkpoint_id']}/resume",
        json={"user_id": "u_1001", "session_id": "sess_resume"},
    )
    resume_body = resume.json()

    assert resume.status_code == 200
    assert resume_body["status"] == "RESUME_READY"
    assert resume_body["parent_run_id"] == body["run_id"]
    assert resume_body["pending_action_id"] == body["pending_action_id"]
    assert _tool_call_count(db_path, resume_body["run_id"]) == 0

    traces = client.get(f"/api/runs/{resume_body['run_id']}/traces").json()
    trace_nodes = {trace["node_name"] for trace in traces}
    assert "resume_action_plan_validation" in trace_nodes
    assert "resume_policy_review" in trace_nodes
    assert "checkpoint_resume_ready" in trace_nodes

    policy_logs = client.get(
        f"/api/runs/{resume_body['run_id']}/policy-logs"
    ).json()
    assert policy_logs[0]["decision"] == "CONFIRM_REQUIRED"


def test_resume_rejects_user_and_session_mismatch(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    chat = client.post(
        "/api/chat",
        json={
            "session_id": "sess_resume",
            "user_id": "u_1001",
            "message": "订单 O10086 的地址填错了，帮我改一下",
        },
    ).json()

    wrong_user = client.post(
        f"/api/checkpoints/{chat['checkpoint_id']}/resume",
        json={"user_id": "u_9999", "session_id": "sess_resume"},
    )
    wrong_session = client.post(
        f"/api/checkpoints/{chat['checkpoint_id']}/resume",
        json={"user_id": "u_1001", "session_id": "sess_other"},
    )

    assert wrong_user.status_code == 403
    assert wrong_session.status_code == 403


def test_cancel_checkpoint_cancels_pending_action(tmp_path: Path) -> None:
    client, db_path = _client(tmp_path)
    chat = client.post(
        "/api/chat",
        json={
            "session_id": "sess_resume",
            "user_id": "u_1001",
            "message": "订单 O10086 的地址填错了，帮我改一下",
        },
    ).json()

    cancel = client.post(
        f"/api/checkpoints/{chat['checkpoint_id']}/cancel",
        json={"user_id": "u_1001", "session_id": "sess_resume"},
    )

    assert cancel.status_code == 200
    assert cancel.json()["status"] == "CANCELLED"
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT status FROM pending_actions WHERE pending_action_id = ?",
            (chat["pending_action_id"],),
        ).fetchone()
    assert row["status"] == "CANCELLED"


def _client(tmp_path: Path):
    db_path = tmp_path / "runtime.db"
    runtime_store = get_runtime_store(db_path=db_path)
    trace_service = TraceService(db_path=db_path)
    repository = RepositoryService(mock_dir=MOCK_DIR, db_path=db_path)
    policy_service = PolicyService(repository=repository)
    pending_action_service = PendingActionService(db_path=db_path)
    checkpoint_service = CheckpointService(db_path=db_path)
    resume_service = ResumeService(
        db_path=db_path,
        checkpoint_service=checkpoint_service,
        pending_action_service=pending_action_service,
        trace_service=trace_service,
        policy_service=policy_service,
    )
    tool_gateway = ToolGateway(db_path=db_path, mock_dir=MOCK_DIR)

    app.dependency_overrides[get_chat_trace_service] = lambda: trace_service
    app.dependency_overrides[get_intent_classifier] = lambda: RuleBasedIntentClassifier()
    app.dependency_overrides[get_action_planner] = lambda: RuleBasedActionPlanner()
    app.dependency_overrides[get_action_plan_validator] = lambda: ActionPlanValidator()
    app.dependency_overrides[get_chat_policy_service] = lambda: policy_service
    app.dependency_overrides[get_chat_tool_gateway] = lambda: tool_gateway
    app.dependency_overrides[get_failure_handler] = lambda: FailureHandler(db_path=db_path)
    app.dependency_overrides[get_chat_pending_action_service] = (
        lambda: pending_action_service
    )
    app.dependency_overrides[get_confirm_pending_action_service] = (
        lambda: pending_action_service
    )
    app.dependency_overrides[get_confirm_trace_service] = lambda: trace_service
    app.dependency_overrides[get_confirm_policy_service] = lambda: policy_service
    app.dependency_overrides[get_confirm_tool_gateway] = lambda: tool_gateway
    app.dependency_overrides[get_checkpoint_service] = lambda: checkpoint_service
    app.dependency_overrides[get_resume_service] = lambda: resume_service
    app.dependency_overrides[get_observability_runtime_store] = lambda: runtime_store

    return TestClient(app), db_path


def _tool_call_count(db_path: Path, run_id: str) -> int:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM tool_call_logs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    return int(row[0])
