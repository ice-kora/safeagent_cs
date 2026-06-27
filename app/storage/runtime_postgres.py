from typing import Any

from app.storage.runtime_config import (
    RUNTIME_BACKEND_POSTGRES,
    RuntimePostgresConfigurationError,
)
from app.storage.runtime_sqlite import (
    _agent_trace_values,
    _checkpoint_event_values,
    _checkpoint_values,
    _failure_log_values,
    _pending_action_event_values,
    _pending_action_values,
    _policy_log_values,
    _resume_attempt_values,
    _tool_call_log_values,
)


RUNTIME_POSTGRES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    parent_run_id TEXT,
    pending_action_id TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_traces (
    trace_node_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    parent_run_id TEXT,
    session_id TEXT NOT NULL,
    node_name TEXT NOT NULL,
    input_json TEXT NOT NULL,
    output_json TEXT NOT NULL,
    status TEXT NOT NULL,
    error_type TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS policy_logs (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    request_id TEXT,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT,
    tenant_id TEXT,
    action TEXT,
    tool_name TEXT,
    target_type TEXT,
    target_id TEXT,
    decision TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    reason TEXT,
    code TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE policy_logs ADD COLUMN IF NOT EXISTS request_id TEXT;
ALTER TABLE policy_logs ADD COLUMN IF NOT EXISTS tool_name TEXT;
ALTER TABLE policy_logs ADD COLUMN IF NOT EXISTS code TEXT;

CREATE TABLE IF NOT EXISTS tool_call_logs (
    id TEXT PRIMARY KEY,
    tool_call_id TEXT,
    idempotency_key TEXT,
    action_fingerprint TEXT,
    run_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    attempt_no INTEGER NOT NULL,
    tool_args_json TEXT NOT NULL,
    tool_result_summary_json TEXT NOT NULL,
    status TEXT NOT NULL,
    failure_type TEXT,
    latency_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pending_action_events (
    event_id TEXT PRIMARY KEY,
    pending_action_id TEXT NOT NULL,
    run_id TEXT,
    parent_run_id TEXT,
    session_id TEXT,
    user_id TEXT,
    tenant_id TEXT,
    event_type TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT,
    reason TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    parent_run_id TEXT,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    current_node TEXT NOT NULL,
    checkpoint_type TEXT NOT NULL,
    state_snapshot_json TEXT NOT NULL,
    resume_policy_json TEXT NOT NULL,
    status TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checkpoint_events (
    event_id TEXT PRIMARY KEY,
    checkpoint_id TEXT NOT NULL,
    run_id TEXT,
    parent_run_id TEXT,
    session_id TEXT,
    user_id TEXT,
    event_type TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT,
    reason TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resume_attempts (
    attempt_id TEXT PRIMARY KEY,
    checkpoint_id TEXT NOT NULL,
    run_id TEXT,
    parent_run_id TEXT,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS failure_logs (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    failure_type TEXT NOT NULL,
    source TEXT NOT NULL,
    retryable INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    fallback_action TEXT,
    final_status TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS security_logs (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    user_id TEXT,
    risk_type TEXT NOT NULL,
    raw_message_summary TEXT,
    normalized_message_summary TEXT,
    decision TEXT,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pending_actions (
    pending_action_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    action_plan_json TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    status TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    source_run_id TEXT,
    parent_run_id TEXT,
    pending_action_id TEXT,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_session_id
    ON agent_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_traces_run_id
    ON agent_traces(run_id);
CREATE INDEX IF NOT EXISTS idx_policy_logs_run_id
    ON policy_logs(run_id);
CREATE INDEX IF NOT EXISTS idx_tool_call_logs_run_id
    ON tool_call_logs(run_id);
CREATE INDEX IF NOT EXISTS idx_tool_call_logs_tool_call_id
    ON tool_call_logs(tool_call_id);
CREATE INDEX IF NOT EXISTS idx_tool_call_logs_idempotency_key
    ON tool_call_logs(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_failure_logs_run_id
    ON failure_logs(run_id);
CREATE INDEX IF NOT EXISTS idx_security_logs_run_id
    ON security_logs(run_id);
CREATE INDEX IF NOT EXISTS idx_pending_actions_user_status
    ON pending_actions(user_id, status);
CREATE INDEX IF NOT EXISTS idx_pending_action_events_pending_action_id
    ON pending_action_events(pending_action_id);
CREATE INDEX IF NOT EXISTS idx_pending_action_events_run_id
    ON pending_action_events(run_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_user_status
    ON checkpoints(user_id, status);
CREATE INDEX IF NOT EXISTS idx_checkpoints_session_status
    ON checkpoints(session_id, status);
CREATE INDEX IF NOT EXISTS idx_checkpoint_events_checkpoint_id
    ON checkpoint_events(checkpoint_id);
CREATE INDEX IF NOT EXISTS idx_resume_attempts_checkpoint_id
    ON resume_attempts(checkpoint_id);
CREATE INDEX IF NOT EXISTS idx_tickets_user_status
    ON tickets(user_id, status);
CREATE INDEX IF NOT EXISTS idx_tickets_idempotency_status
    ON tickets(idempotency_key, status);
"""


class PostgresRuntimeStore:
    """PostgreSQL Runtime Store。

    只负责运行时表，不接真实业务平台，不保存敏感明文。
    """

    backend = RUNTIME_BACKEND_POSTGRES

    def __init__(self, database_url: str | None) -> None:
        if not database_url:
            raise RuntimePostgresConfigurationError(
                "SAFEAGENT_RUNTIME_BACKEND=postgres requires "
                "SAFEAGENT_RUNTIME_DATABASE_URL or DATABASE_URL"
            )
        self.database_url = database_url
        self.init_schema()

    def init_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(RUNTIME_POSTGRES_SCHEMA_SQL)
            connection.commit()

    def get_open_ticket_by_idempotency_key(
        self, idempotency_key: str
    ) -> dict[str, Any] | None:
        row = self._fetchone(
            """
            SELECT id, user_id, type, status, risk_level, idempotency_key,
                   source_run_id, parent_run_id, pending_action_id
            FROM tickets
            WHERE idempotency_key = %s
              AND status IN ('OPEN', 'PROCESSING')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (idempotency_key,),
        )
        return _row_to_dict(row)

    def insert_ticket(self, ticket: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO tickets (
                id, user_id, type, status, risk_level, idempotency_key,
                source_run_id, parent_run_id, pending_action_id, description
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                ticket["id"],
                ticket["user_id"],
                ticket["type"],
                ticket["status"],
                ticket["risk_level"],
                ticket["idempotency_key"],
                ticket.get("source_run_id"),
                ticket.get("parent_run_id"),
                ticket.get("pending_action_id"),
                ticket.get("description"),
            ),
        )

    def create_pending_action(self, pending_action: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO pending_actions (
                pending_action_id, session_id, source_run_id, user_id,
                action_plan_json, risk_level, status, expires_at,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            _pending_action_values(pending_action),
        )

    def get_pending_action(self, pending_action_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            """
            SELECT pending_action_id, session_id, source_run_id, user_id,
                   action_plan_json, risk_level, status, expires_at,
                   created_at, updated_at
            FROM pending_actions
            WHERE pending_action_id = %s
            """,
            (pending_action_id,),
        )
        return _row_to_dict(row)

    def get_pending_action_status_context(
        self, pending_action_id: str
    ) -> dict[str, Any] | None:
        row = self._fetchone(
            """
            SELECT status, session_id, user_id, source_run_id
            FROM pending_actions
            WHERE pending_action_id = %s
            """,
            (pending_action_id,),
        )
        return _row_to_dict(row)

    def update_pending_action_status(
        self,
        pending_action_id: str,
        status: str,
        updated_at: str,
    ) -> int:
        return self._execute(
            """
            UPDATE pending_actions
            SET status = %s, updated_at = %s
            WHERE pending_action_id = %s
            """,
            (status, updated_at, pending_action_id),
        )

    def insert_pending_action_event(self, event: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO pending_action_events (
                event_id, pending_action_id, run_id, parent_run_id,
                session_id, user_id, tenant_id, event_type,
                old_status, new_status, reason, metadata_json, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            _pending_action_event_values(event),
        )

    def list_pending_action_events(
        self, pending_action_id: str
    ) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT event_id, pending_action_id, run_id, parent_run_id,
                   session_id, user_id, tenant_id, event_type,
                   old_status, new_status, reason, metadata_json, created_at
            FROM pending_action_events
            WHERE pending_action_id = %s
            ORDER BY created_at ASC
            """,
            (pending_action_id,),
        )
        return [_row_to_dict(row) for row in rows]

    def list_pending_actions(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if user_id:
            conditions.append("user_id = %s")
            params.append(user_id)
        if session_id:
            conditions.append("session_id = %s")
            params.append(session_id)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._fetchall(
            f"""
            SELECT pending_action_id, session_id, source_run_id, user_id,
                   action_plan_json, risk_level, status, expires_at,
                   created_at, updated_at
            FROM pending_actions
            {where_clause}
            ORDER BY created_at DESC
            """,
            tuple(params),
        )
        return [_row_to_dict(row) for row in rows]

    def insert_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO checkpoints (
                checkpoint_id, run_id, parent_run_id, session_id, user_id,
                current_node, checkpoint_type, state_snapshot_json,
                resume_policy_json, status, expires_at, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            _checkpoint_values(checkpoint),
        )

    def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            """
            SELECT checkpoint_id, run_id, parent_run_id, session_id, user_id,
                   current_node, checkpoint_type, state_snapshot_json,
                   resume_policy_json, status, expires_at, created_at, updated_at
            FROM checkpoints
            WHERE checkpoint_id = %s
            """,
            (checkpoint_id,),
        )
        return _row_to_dict(row)

    def list_checkpoints(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        statuses: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if user_id:
            conditions.append("user_id = %s")
            params.append(user_id)
        if session_id:
            conditions.append("session_id = %s")
            params.append(session_id)
        if statuses:
            placeholders = ", ".join("%s" for _ in statuses)
            conditions.append(f"status IN ({placeholders})")
            params.extend(statuses)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._fetchall(
            f"""
            SELECT checkpoint_id, run_id, parent_run_id, session_id, user_id,
                   current_node, checkpoint_type, state_snapshot_json,
                   resume_policy_json, status, expires_at, created_at, updated_at
            FROM checkpoints
            {where_clause}
            ORDER BY created_at DESC, checkpoint_id DESC
            """,
            tuple(params),
        )
        return [_row_to_dict(row) for row in rows]

    def update_checkpoint_status(
        self,
        checkpoint_id: str,
        status: str,
        updated_at: str,
    ) -> int:
        return self._execute(
            """
            UPDATE checkpoints
            SET status = %s, updated_at = %s
            WHERE checkpoint_id = %s
            """,
            (status, updated_at, checkpoint_id),
        )

    def insert_checkpoint_event(self, event: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO checkpoint_events (
                event_id, checkpoint_id, run_id, parent_run_id,
                session_id, user_id, event_type, old_status, new_status,
                reason, metadata_json, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            _checkpoint_event_values(event),
        )

    def list_checkpoint_events(self, checkpoint_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT event_id, checkpoint_id, run_id, parent_run_id,
                   session_id, user_id, event_type, old_status, new_status,
                   reason, metadata_json, created_at
            FROM checkpoint_events
            WHERE checkpoint_id = %s
            ORDER BY created_at ASC, event_id ASC
            """,
            (checkpoint_id,),
        )
        return [_row_to_dict(row) for row in rows]

    def insert_resume_attempt(self, attempt: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO resume_attempts (
                attempt_id, checkpoint_id, run_id, parent_run_id,
                session_id, user_id, status, reason, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            _resume_attempt_values(attempt),
        )

    def insert_tool_call_log(self, log: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO tool_call_logs (
                id, tool_call_id, idempotency_key, action_fingerprint,
                run_id, session_id, tool_name, attempt_no,
                tool_args_json, tool_result_summary_json,
                status, failure_type, latency_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            _tool_call_log_values(log),
        )

    def list_tool_call_logs(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT id, tool_call_id, idempotency_key, action_fingerprint,
                   run_id, session_id, tool_name, attempt_no,
                   tool_args_json, tool_result_summary_json,
                   status, failure_type, latency_ms, created_at
            FROM tool_call_logs
            WHERE run_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (run_id,),
        )
        return [_row_to_dict(row) for row in rows]

    def insert_agent_run(self, run: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO agent_runs (
                run_id, session_id, user_id, request_id,
                parent_run_id, pending_action_id, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run["run_id"],
                run["session_id"],
                run["user_id"],
                run["request_id"],
                run.get("parent_run_id"),
                run.get("pending_action_id"),
                run["status"],
            ),
        )

    def get_agent_run(self, run_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            """
            SELECT run_id, session_id, user_id, request_id,
                   parent_run_id, pending_action_id, status
            FROM agent_runs
            WHERE run_id = %s
            """,
            (run_id,),
        )
        return _row_to_dict(row)

    def update_agent_run_status(self, run_id: str, status: str) -> int:
        return self._execute(
            """
            UPDATE agent_runs
            SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE run_id = %s
            """,
            (status, run_id),
        )

    def insert_agent_trace(self, trace: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO agent_traces (
                trace_node_id, run_id, parent_run_id, session_id,
                node_name, input_json, output_json, status, error_type
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            _agent_trace_values(trace),
        )

    def list_agent_traces(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT trace_node_id, run_id, parent_run_id, session_id,
                   node_name, input_json, output_json, status,
                   error_type, created_at
            FROM agent_traces
            WHERE run_id = %s
            ORDER BY created_at ASC
            """,
            (run_id,),
        )
        return [_row_to_dict(row) for row in rows]

    def insert_policy_log(self, log: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO policy_logs (
                id, run_id, request_id, session_id, user_id, role,
                tenant_id, action, tool_name, target_type, target_id,
                decision, risk_level, reason, code, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            _policy_log_values(log),
        )

    def list_policy_logs(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT id, run_id, request_id, session_id, user_id, role,
                   tenant_id, action, tool_name, target_type, target_id,
                   decision, risk_level, reason, code, created_at
            FROM policy_logs
            WHERE run_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (run_id,),
        )
        return [_row_to_dict(row) for row in rows]

    def insert_failure_log(self, log: dict[str, Any]) -> None:
        self._execute(
            """
            INSERT INTO failure_logs (
                id, run_id, session_id, failure_type, source,
                retryable, retry_count, fallback_action, final_status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            _failure_log_values(log),
        )

    def list_failure_logs(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT id, run_id, session_id, failure_type, source,
                   retryable, retry_count, fallback_action, final_status,
                   created_at
            FROM failure_logs
            WHERE run_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (run_id,),
        )
        return [_row_to_dict(row) for row in rows]

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL runtime backend requires optional dependency psycopg"
            ) from exc
        return psycopg.connect(
            self.database_url,
            connect_timeout=10,
            row_factory=dict_row,
        )

    def _execute(self, sql: str, params: tuple[Any, ...]) -> int:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                rowcount = cursor.rowcount
            connection.commit()
        return rowcount

    def _fetchone(self, sql: str, params: tuple[Any, ...]):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchone()

    def _fetchall(self, sql: str, params: tuple[Any, ...]):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    return dict(row)
