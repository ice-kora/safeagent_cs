import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.observability import get_observability_runtime_store
from app.main import app
from app.storage.db import get_connection
from app.storage.runtime_store import get_runtime_store


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_observability_api_reads_runtime_records_and_sanitizes_sensitive_data(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "runtime.db"
    store = get_runtime_store(db_path=db_path)
    run_id = "run_obs_v08"
    session_id = "sess_obs_v08"
    user_id = "u_1001"

    store.insert_agent_run(
        {
            "run_id": run_id,
            "session_id": session_id,
            "user_id": user_id,
            "request_id": "req_obs_v08",
            "parent_run_id": None,
            "pending_action_id": None,
            "status": "SUCCESS",
        }
    )
    store.insert_agent_trace(
        {
            "trace_node_id": "trace_obs_v08",
            "run_id": run_id,
            "parent_run_id": None,
            "session_id": session_id,
            "node_name": "unit_trace",
            "input_json": json.dumps(
                {
                    "message": "phone 13800138000",
                    "message_with_location": "请改到北京市朝阳区幸福路1号",
                    "system_note": "system prompt: never show this",
                }
            ),
            "output_json": json.dumps({"token": "secret-token"}),
            "status": "SUCCESS",
            "error_type": None,
        }
    )
    store.insert_tool_call_log(
        {
            "id": "tcl_obs_v08",
            "tool_call_id": "tc_obs_v08",
            "idempotency_key": "idem_obs_v08",
            "action_fingerprint": "fp_obs_v08",
            "run_id": run_id,
            "session_id": session_id,
            "tool_name": "order_tool.change_address",
            "attempt_no": 1,
            "tool_args_json": json.dumps(
                {
                    "new_address": "No. 1 Secret Street",
                    "api_key": "key-123",
                    "card": "4111111111111111",
                }
            ),
            "tool_result_summary_json": json.dumps({"summary": "ok"}),
            "status": "SUCCESS",
            "failure_type": None,
            "latency_ms": 3,
        }
    )
    store.insert_failure_log(
        {
            "id": "fl_obs_v08",
            "run_id": run_id,
            "session_id": session_id,
            "failure_type": "TOOL_TIMEOUT",
            "source": "tool_gateway",
            "retryable": 1,
            "retry_count": 1,
            "fallback_action": "retry",
            "final_status": "RECOVERED",
        }
    )
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO policy_logs (
                id, run_id, session_id, user_id, action, target_type,
                target_id, decision, risk_level, reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "pl_obs_v08",
                run_id,
                session_id,
                user_id,
                "query_policy",
                "policy",
                "shipping",
                "ALLOW",
                "L0",
                "read-only policy query",
            ),
        )
        connection.commit()

    app.dependency_overrides[get_observability_runtime_store] = lambda: store
    client = TestClient(app)

    assert client.get(f"/api/runs/{run_id}").json()["run_id"] == run_id
    traces = client.get(f"/api/runs/{run_id}/traces").json()
    tool_calls = client.get(f"/api/runs/{run_id}/tool-calls").json()
    policy_logs = client.get(f"/api/runs/{run_id}/policy-logs").json()
    failure_logs = client.get(f"/api/runs/{run_id}/failure-logs").json()

    assert traces[0]["input"]["message"] == "phone ***"
    assert traces[0]["input"]["message_with_location"] == "***"
    assert traces[0]["input"]["system_note"] == "system_prompt=***"
    assert traces[0]["output"]["token"] == "***"
    assert tool_calls[0]["tool_args"]["new_address"] == "***"
    assert tool_calls[0]["tool_args"]["api_key"] == "***"
    assert tool_calls[0]["tool_args"]["card"] == "***"
    assert policy_logs[0]["decision"] == "ALLOW"
    assert failure_logs[0]["failure_type"] == "TOOL_TIMEOUT"

    serialized = json.dumps(
        {
            "traces": traces,
            "tool_calls": tool_calls,
            "policy_logs": policy_logs,
            "failure_logs": failure_logs,
        },
        ensure_ascii=False,
    )
    assert "13800138000" not in serialized
    assert "never show this" not in serialized
    assert "4111111111111111" not in serialized
    assert "No. 1 Secret Street" not in serialized


def test_pending_actions_observability_endpoint_filters_and_sanitizes(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "runtime.db"
    store = get_runtime_store(db_path=db_path)
    store.create_pending_action(
        {
            "pending_action_id": "pa_obs_v08",
            "session_id": "sess_obs_v08",
            "source_run_id": "run_obs_v08",
            "user_id": "u_1001",
            "action_plan_json": json.dumps(
                {
                    "intent": "address_change",
                    "action": "change_address",
                    "tool_args": {"address": "No. 1 Secret Street"},
                }
            ),
            "risk_level": "L3",
            "status": "PENDING",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
    )
    app.dependency_overrides[get_observability_runtime_store] = lambda: store
    client = TestClient(app)

    response = client.get(
        "/api/pending-actions",
        params={"user_id": "u_1001", "session_id": "sess_obs_v08"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body[0]["pending_action_id"] == "pa_obs_v08"
    assert body[0]["action_plan"]["tool_args"]["address"] == "***"


def test_get_unknown_run_returns_404(tmp_path: Path) -> None:
    store = get_runtime_store(db_path=tmp_path / "runtime.db")
    app.dependency_overrides[get_observability_runtime_store] = lambda: store
    client = TestClient(app)

    response = client.get("/api/runs/run_missing")

    assert response.status_code == 404
