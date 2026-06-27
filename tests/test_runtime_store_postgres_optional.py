import os
from uuid import uuid4

import pytest

from app.storage.runtime_config import RUNTIME_BACKEND_POSTGRES
from app.storage.runtime_store import get_runtime_store


def _postgres_store_or_skip(monkeypatch):
    database_url = os.getenv("SAFEAGENT_RUNTIME_DATABASE_URL") or os.getenv(
        "DATABASE_URL"
    )
    if not database_url:
        pytest.skip("runtime PostgreSQL URL is not configured")
    monkeypatch.setenv("SAFEAGENT_RUNTIME_BACKEND", RUNTIME_BACKEND_POSTGRES)
    try:
        return get_runtime_store(backend=RUNTIME_BACKEND_POSTGRES, database_url=database_url)
    except RuntimeError as exc:
        pytest.skip(str(exc))


def test_runtime_postgres_optional_ticket_and_pending_action(monkeypatch) -> None:
    store = _postgres_store_or_skip(monkeypatch)
    suffix = uuid4().hex[:8]
    ticket_id = f"tk_pg_{suffix}"
    idempotency_key = f"u_1001:request_refund:order:O{suffix}"
    pending_action_id = f"pa_pg_{suffix}"

    store.insert_ticket(
        {
            "id": ticket_id,
            "user_id": "u_1001",
            "type": "refund",
            "status": "OPEN",
            "risk_level": "L4",
            "idempotency_key": idempotency_key,
            "source_run_id": "run_pg",
            "parent_run_id": None,
            "pending_action_id": None,
            "description": "safe",
        }
    )
    store.create_pending_action(
        {
            "pending_action_id": pending_action_id,
            "session_id": "sess_pg",
            "source_run_id": "run_pg",
            "user_id": "u_1001",
            "action_plan_json": "{}",
            "risk_level": "L3",
            "status": "PENDING",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
    )

    assert store.get_open_ticket_by_idempotency_key(idempotency_key)["id"] == ticket_id
    assert store.get_pending_action(pending_action_id)["status"] == "PENDING"


def test_runtime_postgres_optional_logs_and_trace(monkeypatch) -> None:
    store = _postgres_store_or_skip(monkeypatch)
    suffix = uuid4().hex[:8]
    run_id = f"run_pg_{suffix}"
    trace_id = f"tn_pg_{suffix}"

    store.insert_agent_run(
        {
            "run_id": run_id,
            "session_id": "sess_pg",
            "user_id": "u_1001",
            "request_id": f"req_pg_{suffix}",
            "parent_run_id": None,
            "pending_action_id": None,
            "status": "RUNNING",
        }
    )
    store.insert_agent_trace(
        {
            "trace_node_id": trace_id,
            "run_id": run_id,
            "parent_run_id": None,
            "session_id": "sess_pg",
            "node_name": "test_node",
            "input_json": "{}",
            "output_json": "{}",
            "status": "SUCCESS",
            "error_type": None,
        }
    )
    store.insert_failure_log(
        {
            "id": f"fl_pg_{suffix}",
            "run_id": run_id,
            "session_id": "sess_pg",
            "failure_type": "TOOL_TIMEOUT",
            "source": "tool_gateway",
            "retryable": 1,
            "retry_count": 1,
            "fallback_action": "RETRY",
            "final_status": "FAILED",
        }
    )

    assert store.get_agent_run(run_id)["status"] == "RUNNING"
    assert store.list_agent_traces(run_id)[0]["trace_node_id"] == trace_id
