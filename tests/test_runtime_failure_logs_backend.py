from pathlib import Path
from uuid import uuid4

from app.core.tool_result import ToolError, ToolResult
from app.services.failure_handler import FailureHandler
from app.storage.db import get_connection
from app.storage.runtime_config import RUNTIME_BACKEND_POSTGRES, get_runtime_database_settings
from app.storage.runtime_store import get_runtime_store


def _fetch_failure_log(db_path: Path, run_id: str):
    store = get_runtime_store(db_path=db_path)
    if store.backend == RUNTIME_BACKEND_POSTGRES:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(get_runtime_database_settings().database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT failure_type, retryable, retry_count, final_status
                    FROM failure_logs
                    WHERE run_id = %s
                    LIMIT 1
                    """,
                    (run_id,),
                )
                return cursor.fetchone()

    with get_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT failure_type, retryable, retry_count, final_status
            FROM failure_logs
            WHERE run_id = ?
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()


def test_failure_handler_writes_failure_logs_via_runtime_store(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.db"
    run_id = f"run_{uuid4().hex}"
    handler = FailureHandler(db_path=db_path)

    handler.handle_tool_result(
        run_id=run_id,
        session_id="sess_001",
        tool_result=ToolResult(
            success=False,
            tool_name="knowledge_tool.query_policy",
            error_type="TOOL_TIMEOUT",
            error=ToolError(
                failure_type="TOOL_TIMEOUT",
                message="timeout",
                retryable=True,
            ),
        ),
    )

    row = _fetch_failure_log(db_path, run_id)

    assert row["failure_type"] == "TOOL_TIMEOUT"
    assert row["retryable"] == 1
    assert row["retry_count"] == 0
    assert row["final_status"] == "RETRY_REQUIRED"
