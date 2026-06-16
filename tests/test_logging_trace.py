import sqlite3
from pathlib import Path

from app.core.ids import generate_request_id
from app.services.logging_service import LoggingService
from app.services.trace_service import TraceService
from app.storage.db import init_db


def test_init_db_creates_required_tables(tmp_path: Path) -> None:
    db_path = init_db(tmp_path / "test.db")

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()

    table_names = {row[0] for row in rows}
    assert {
        "agent_runs",
        "agent_traces",
        "policy_logs",
        "tool_call_logs",
        "failure_logs",
        "security_logs",
        "pending_actions",
        "tickets",
    }.issubset(table_names)


def test_init_db_creates_required_indexes(tmp_path: Path) -> None:
    db_path = init_db(tmp_path / "test.db")

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        ).fetchall()

    index_names = {row[0] for row in rows}
    assert {
        "idx_agent_runs_session_id",
        "idx_agent_traces_run_id",
        "idx_policy_logs_run_id",
        "idx_tool_call_logs_run_id",
        "idx_failure_logs_run_id",
        "idx_security_logs_run_id",
        "idx_pending_actions_user_status",
        "idx_tickets_user_status",
        "idx_tickets_idempotency_status",
    }.issubset(index_names)


def test_logging_service_writes_sanitized_application_log(tmp_path: Path) -> None:
    log_path = tmp_path / "application.log"
    logging_service = LoggingService(log_path=log_path)

    logging_service.info(
        "test_event",
        {
            "phone": "13800001234",
            "address": "Henan Zhengzhou Jinshui Road 100",
            "message": "token=secret-token-value",
        },
    )

    content = log_path.read_text(encoding="utf-8")
    assert "test_event" in content
    assert "13800001234" not in content
    assert "Henan Zhengzhou Jinshui Road 100" not in content
    assert "secret-token-value" not in content


def test_trace_service_creates_run_and_trace_node(tmp_path: Path) -> None:
    logging_service = LoggingService(log_path=tmp_path / "application.log")
    trace_service = TraceService(
        db_path=tmp_path / "test.db",
        logging_service=logging_service,
    )

    run_id = trace_service.start_run(
        session_id="s_001",
        user_id="u_1001",
        request_id=generate_request_id(),
    )
    trace_node_id = trace_service.append_trace(
        run_id=run_id,
        node_name="unit_test_node",
        input_json={"phone": "13800001234", "message": "hello"},
        output_json={"result": "ok"},
    )
    traces = trace_service.get_traces(run_id)

    assert run_id.startswith("run_")
    assert trace_node_id.startswith("tn_")
    assert len(traces) == 1
    assert traces[0]["node_name"] == "unit_test_node"
    assert traces[0]["input_json"]["phone"] == "***"
    assert traces[0]["output_json"] == {"result": "ok"}


def test_trace_service_can_finish_run(tmp_path: Path) -> None:
    trace_service = TraceService(
        db_path=tmp_path / "test.db",
        logging_service=LoggingService(log_path=tmp_path / "application.log"),
    )
    run_id = trace_service.start_run(
        session_id="s_001",
        user_id="u_1001",
        request_id=generate_request_id(),
    )

    trace_service.finish_run(run_id)

    with sqlite3.connect(tmp_path / "test.db") as connection:
        row = connection.execute(
            "SELECT status, updated_at FROM agent_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    assert row[0] == "SUCCESS"
    assert row[1] is not None


def test_trace_service_can_fail_run(tmp_path: Path) -> None:
    trace_service = TraceService(
        db_path=tmp_path / "test.db",
        logging_service=LoggingService(log_path=tmp_path / "application.log"),
    )
    run_id = trace_service.start_run(
        session_id="s_001",
        user_id="u_1001",
        request_id=generate_request_id(),
    )

    trace_service.fail_run(run_id, error_type="UNIT_TEST_ERROR")

    with sqlite3.connect(tmp_path / "test.db") as connection:
        row = connection.execute(
            "SELECT status, updated_at FROM agent_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    assert row[0] == "FAILED"
    assert row[1] is not None


def test_trace_service_reports_missing_run_clearly(tmp_path: Path) -> None:
    trace_service = TraceService(
        db_path=tmp_path / "test.db",
        logging_service=LoggingService(log_path=tmp_path / "application.log"),
    )

    try:
        trace_service.finish_run("run_missing")
    except ValueError as exc:
        assert "run_id 不存在" in str(exc)
        assert "run_missing" in str(exc)
    else:
        raise AssertionError("finish_run should fail for missing run_id")
