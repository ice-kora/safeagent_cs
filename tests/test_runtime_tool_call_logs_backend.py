from pathlib import Path
from uuid import uuid4

from app.services.tool_gateway import ToolGateway
from app.storage.db import get_connection
from app.storage.runtime_config import RUNTIME_BACKEND_POSTGRES, get_runtime_database_settings
from app.storage.runtime_store import get_runtime_store


def _fetch_tool_call_log(db_path: Path, run_id: str):
    store = get_runtime_store(db_path=db_path)
    if store.backend == RUNTIME_BACKEND_POSTGRES:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(get_runtime_database_settings().database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT tool_call_id, idempotency_key, action_fingerprint,
                           attempt_no, status
                    FROM tool_call_logs
                    WHERE run_id = %s
                    LIMIT 1
                    """,
                    (run_id,),
                )
                return cursor.fetchone()

    with get_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT tool_call_id, idempotency_key, action_fingerprint,
                   attempt_no, status
            FROM tool_call_logs
            WHERE run_id = ?
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()


def test_tool_gateway_writes_tool_call_logs_via_runtime_store(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    run_id = f"run_{uuid4().hex}"
    gateway = ToolGateway(db_path=db_path)

    result = gateway.call_tool(
        run_id=run_id,
        session_id="sess_001",
        tool_name="knowledge_tool.query_policy",
        tool_args={"query": "退款政策"},
    )

    row = _fetch_tool_call_log(db_path, run_id)

    assert result.success is True
    assert row["tool_call_id"].startswith("tc_")
    assert row["idempotency_key"].startswith("idem_")
    assert row["action_fingerprint"].startswith("af_")
    assert row["attempt_no"] == 1
    assert row["status"] == "SUCCESS"
