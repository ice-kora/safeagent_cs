from pathlib import Path

from app.services.trace_service import TraceService


def test_trace_service_writes_runs_and_traces_via_runtime_store(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    service = TraceService(db_path=db_path)

    run_id = service.start_run(
        session_id="sess_001",
        user_id="u_1001",
        request_id="req_001",
    )
    service.append_trace(
        run_id=run_id,
        node_name="test_node",
        input_json={"message": "hello"},
        output_json={"status": "ok"},
    )
    service.finish_run(run_id)

    traces = service.get_traces(run_id)
    run = service.runtime_store.get_agent_run(run_id)

    assert run["status"] == "SUCCESS"
    assert traces[0]["node_name"] == "test_node"
