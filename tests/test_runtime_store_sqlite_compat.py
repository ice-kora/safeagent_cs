from pathlib import Path

from app.storage.runtime_store import get_runtime_store


def test_sqlite_runtime_store_ticket_operations(tmp_path: Path) -> None:
    store = get_runtime_store(db_path=tmp_path / "runtime.db")
    store.insert_ticket(
        {
            "id": "tk_sqlite",
            "user_id": "u_1001",
            "type": "refund",
            "status": "OPEN",
            "risk_level": "L4",
            "idempotency_key": "u_1001:request_refund:order:O10086",
            "source_run_id": "run_001",
            "parent_run_id": None,
            "pending_action_id": None,
            "description": "safe description",
        }
    )

    ticket = store.get_open_ticket_by_idempotency_key(
        "u_1001:request_refund:order:O10086"
    )

    assert ticket["id"] == "tk_sqlite"
    assert ticket["status"] == "OPEN"


def test_sqlite_runtime_store_pending_action_operations(tmp_path: Path) -> None:
    store = get_runtime_store(db_path=tmp_path / "runtime.db")
    store.create_pending_action(
        {
            "pending_action_id": "pa_sqlite",
            "session_id": "sess_001",
            "source_run_id": "run_001",
            "user_id": "u_1001",
            "action_plan_json": "{}",
            "risk_level": "L3",
            "status": "PENDING",
            "expires_at": "2099-01-01T00:00:00+00:00",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
    )

    assert store.get_pending_action("pa_sqlite")["status"] == "PENDING"
    assert (
        store.update_pending_action_status(
            "pa_sqlite",
            "CANCELLED",
            "2026-01-01T00:01:00+00:00",
        )
        == 1
    )
    assert store.get_pending_action("pa_sqlite")["status"] == "CANCELLED"


def test_sqlite_runtime_store_logs_runs_and_traces(tmp_path: Path) -> None:
    store = get_runtime_store(db_path=tmp_path / "runtime.db")
    store.insert_agent_run(
        {
            "run_id": "run_sqlite",
            "session_id": "sess_001",
            "user_id": "u_1001",
            "request_id": "req_001",
            "parent_run_id": None,
            "pending_action_id": None,
            "status": "RUNNING",
        }
    )
    store.insert_agent_trace(
        {
            "trace_node_id": "tn_sqlite",
            "run_id": "run_sqlite",
            "parent_run_id": None,
            "session_id": "sess_001",
            "node_name": "test_node",
            "input_json": "{}",
            "output_json": "{}",
            "status": "SUCCESS",
            "error_type": None,
        }
    )

    assert store.get_agent_run("run_sqlite")["status"] == "RUNNING"
    assert store.list_agent_traces("run_sqlite")[0]["node_name"] == "test_node"
    assert store.update_agent_run_status("run_sqlite", "SUCCESS") == 1


def test_sqlite_runtime_store_tool_and_failure_logs(tmp_path: Path) -> None:
    store = get_runtime_store(db_path=tmp_path / "runtime.db")
    store.insert_tool_call_log(
        {
            "id": "tcl_sqlite",
            "tool_call_id": "tc_001",
            "idempotency_key": "idem_001",
            "action_fingerprint": "af_001",
            "run_id": "run_001",
            "session_id": "sess_001",
            "tool_name": "knowledge_tool.query_policy",
            "attempt_no": 1,
            "tool_args_json": "{}",
            "tool_result_summary_json": "{}",
            "status": "SUCCESS",
            "failure_type": None,
            "latency_ms": 1,
        }
    )
    store.insert_failure_log(
        {
            "id": "fl_sqlite",
            "run_id": "run_001",
            "session_id": "sess_001",
            "failure_type": "TOOL_TIMEOUT",
            "source": "tool_gateway",
            "retryable": 1,
            "retry_count": 1,
            "fallback_action": "RETRY",
            "final_status": "FAILED",
        }
    )

    assert store.backend == "sqlite"
