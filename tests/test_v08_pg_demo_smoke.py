import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


def test_v08_demo_profile_postgres_chat_confirm_observability(monkeypatch) -> None:
    database_url = os.getenv("DATABASE_URL")
    runtime_url = os.getenv("SAFEAGENT_RUNTIME_DATABASE_URL") or database_url
    if not database_url:
        pytest.skip("DATABASE_URL is not configured for v0.8 PG demo smoke")
    if not runtime_url:
        pytest.skip(
            "SAFEAGENT_RUNTIME_DATABASE_URL or DATABASE_URL is not configured "
            "for v0.8 PG demo smoke"
        )

    monkeypatch.setenv("SAFEAGENT_PROFILE", "demo")
    monkeypatch.setenv("SAFEAGENT_DB_BACKEND", "postgres")
    monkeypatch.setenv("SAFEAGENT_RUNTIME_BACKEND", "postgres")
    monkeypatch.setenv("SAFEAGENT_RUNTIME_DATABASE_URL", runtime_url)
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_MODE", "workflow")
    monkeypatch.setenv("SAFEAGENT_WORKFLOW_ENGINE", "langgraph")
    monkeypatch.setenv("SAFEAGENT_LLM_MODE", "rule")
    monkeypatch.setenv("SAFEAGENT_TOOL_BACKEND", "mock")

    from app.core.config import get_settings
    from app.main import app
    from app.storage.postgres import PostgresBackend, PostgresBackendError
    from app.storage.runtime_store import get_runtime_store

    settings = get_settings()
    assert settings.profile == "demo"
    assert settings.db_backend == "postgres"
    assert settings.runtime_backend == "postgres"
    assert settings.workflow_mode == "workflow"
    assert settings.workflow_engine == "langgraph"

    try:
        platform_backend = PostgresBackend(database_url)
        platform_backend.init_schema()
        platform_backend.seed_users_orders()
        get_runtime_store(backend="postgres", database_url=runtime_url)
    except (PostgresBackendError, RuntimeError) as exc:
        pytest.skip(str(exc))

    client = TestClient(app)
    suffix = uuid4().hex[:8]
    session_id = f"sess_pg_demo_{suffix}"

    policy_chat = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "user_id": "u_1001",
            "message": "你们支持七天无理由退货吗？",
        },
    )
    policy_body = policy_chat.json()
    assert policy_chat.status_code == 200
    assert policy_body["status"] in {"SUCCESS", "RECOVERED"}

    policy_run_id = policy_body["run_id"]
    assert client.get(f"/api/runs/{policy_run_id}/traces").json()
    assert client.get(f"/api/runs/{policy_run_id}/tool-calls").json()
    assert client.get(f"/api/runs/{policy_run_id}/policy-logs").json()
    assert isinstance(client.get(f"/api/runs/{policy_run_id}/failure-logs").json(), list)

    pending_chat = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "user_id": "u_1001",
            "message": "订单 O10086 的地址填错了，帮我改一下",
        },
    )
    pending_body = pending_chat.json()
    assert pending_chat.status_code == 200
    assert pending_body["status"] == "CONFIRM_REQUIRED"
    assert pending_body["pending_action_id"]

    confirm_response = client.post(
        "/api/confirm",
        json={
            "pending_action_id": pending_body["pending_action_id"],
            "user_id": "u_1001",
            "session_id": session_id,
            "confirm": False,
        },
    )
    confirm_body = confirm_response.json()
    assert confirm_response.status_code == 200
    assert confirm_body["status"] == "CANCELLED"
    assert client.get(f"/api/runs/{pending_body['run_id']}/policy-logs").json()
    assert client.get(f"/api/runs/{confirm_body['run_id']}/traces").json()
