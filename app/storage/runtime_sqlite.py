from pathlib import Path
from typing import Any

from app.storage.db import get_connection, init_db
from app.storage.runtime_config import RUNTIME_BACKEND_SQLITE


class SQLiteRuntimeStore:
    """SQLite Runtime Store。

    这是当前默认实现，封装旧的 SQLite 读写语义，保证已有 db_path 测试不受影响。
    """

    backend = RUNTIME_BACKEND_SQLITE

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else None
        self.init_schema()

    def init_schema(self) -> None:
        init_db(self.db_path)

    def get_open_ticket_by_idempotency_key(
        self, idempotency_key: str
    ) -> dict[str, Any] | None:
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT id, user_id, type, status, risk_level, idempotency_key,
                       source_run_id, parent_run_id, pending_action_id
                FROM tickets
                WHERE idempotency_key = ?
                  AND status IN ('OPEN', 'PROCESSING')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (idempotency_key,),
            ).fetchone()
        return dict(row) if row else None

    def insert_ticket(self, ticket: dict[str, Any]) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO tickets (
                    id, user_id, type, status, risk_level, idempotency_key,
                    source_run_id, parent_run_id, pending_action_id, description
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            connection.commit()

    def create_pending_action(self, pending_action: dict[str, Any]) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO pending_actions (
                    pending_action_id, session_id, source_run_id, user_id,
                    action_plan_json, risk_level, status, expires_at,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _pending_action_values(pending_action),
            )
            connection.commit()

    def get_pending_action(self, pending_action_id: str) -> dict[str, Any] | None:
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT pending_action_id, session_id, source_run_id, user_id,
                       action_plan_json, risk_level, status, expires_at,
                       created_at, updated_at
                FROM pending_actions
                WHERE pending_action_id = ?
                """,
                (pending_action_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_pending_action_status_context(
        self, pending_action_id: str
    ) -> dict[str, Any] | None:
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT status, session_id, user_id, source_run_id
                FROM pending_actions
                WHERE pending_action_id = ?
                """,
                (pending_action_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_pending_action_status(
        self,
        pending_action_id: str,
        status: str,
        updated_at: str,
    ) -> int:
        with get_connection(self.db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE pending_actions
                SET status = ?, updated_at = ?
                WHERE pending_action_id = ?
                """,
                (status, updated_at, pending_action_id),
            )
            connection.commit()
        return cursor.rowcount

    def insert_pending_action_event(self, event: dict[str, Any]) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO pending_action_events (
                    event_id, pending_action_id, run_id, parent_run_id,
                    session_id, user_id, tenant_id, event_type,
                    old_status, new_status, reason, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _pending_action_event_values(event),
            )
            connection.commit()

    def list_pending_action_events(
        self, pending_action_id: str
    ) -> list[dict[str, Any]]:
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT event_id, pending_action_id, run_id, parent_run_id,
                       session_id, user_id, tenant_id, event_type,
                       old_status, new_status, reason, metadata_json, created_at
                FROM pending_action_events
                WHERE pending_action_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (pending_action_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_pending_actions(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                f"""
                SELECT pending_action_id, session_id, source_run_id, user_id,
                       action_plan_json, risk_level, status, expires_at,
                       created_at, updated_at
                FROM pending_actions
                {where_clause}
                ORDER BY created_at DESC, rowid DESC
                """,
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO checkpoints (
                    checkpoint_id, run_id, parent_run_id, session_id, user_id,
                    current_node, checkpoint_type, state_snapshot_json,
                    resume_policy_json, status, expires_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _checkpoint_values(checkpoint),
            )
            connection.commit()

    def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any] | None:
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT checkpoint_id, run_id, parent_run_id, session_id, user_id,
                       current_node, checkpoint_type, state_snapshot_json,
                       resume_policy_json, status, expires_at, created_at, updated_at
                FROM checkpoints
                WHERE checkpoint_id = ?
                """,
                (checkpoint_id,),
            ).fetchone()
        return dict(row) if row else None

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
            conditions.append("user_id = ?")
            params.append(user_id)
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            conditions.append(f"status IN ({placeholders})")
            params.extend(statuses)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                f"""
                SELECT checkpoint_id, run_id, parent_run_id, session_id, user_id,
                       current_node, checkpoint_type, state_snapshot_json,
                       resume_policy_json, status, expires_at, created_at, updated_at
                FROM checkpoints
                {where_clause}
                ORDER BY created_at DESC, rowid DESC
                """,
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_checkpoint_status(
        self,
        checkpoint_id: str,
        status: str,
        updated_at: str,
    ) -> int:
        with get_connection(self.db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE checkpoints
                SET status = ?, updated_at = ?
                WHERE checkpoint_id = ?
                """,
                (status, updated_at, checkpoint_id),
            )
            connection.commit()
        return cursor.rowcount

    def insert_checkpoint_event(self, event: dict[str, Any]) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO checkpoint_events (
                    event_id, checkpoint_id, run_id, parent_run_id,
                    session_id, user_id, event_type, old_status, new_status,
                    reason, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _checkpoint_event_values(event),
            )
            connection.commit()

    def list_checkpoint_events(self, checkpoint_id: str) -> list[dict[str, Any]]:
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT event_id, checkpoint_id, run_id, parent_run_id,
                       session_id, user_id, event_type, old_status, new_status,
                       reason, metadata_json, created_at
                FROM checkpoint_events
                WHERE checkpoint_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (checkpoint_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_resume_attempt(self, attempt: dict[str, Any]) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO resume_attempts (
                    attempt_id, checkpoint_id, run_id, parent_run_id,
                    session_id, user_id, status, reason, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _resume_attempt_values(attempt),
            )
            connection.commit()

    def insert_tool_call_log(self, log: dict[str, Any]) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO tool_call_logs (
                    id, tool_call_id, idempotency_key, action_fingerprint,
                    run_id, session_id, tool_name, attempt_no,
                    tool_args_json, tool_result_summary_json,
                    status, failure_type, latency_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _tool_call_log_values(log),
            )
            connection.commit()

    def list_tool_call_logs(self, run_id: str) -> list[dict[str, Any]]:
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT id, tool_call_id, idempotency_key, action_fingerprint,
                       run_id, session_id, tool_name, attempt_no,
                       tool_args_json, tool_result_summary_json,
                       status, failure_type, latency_ms, created_at
                FROM tool_call_logs
                WHERE run_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_agent_run(self, run: dict[str, Any]) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    run_id, session_id, user_id, request_id,
                    parent_run_id, pending_action_id, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
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
            connection.commit()

    def get_agent_run(self, run_id: str) -> dict[str, Any] | None:
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT run_id, session_id, user_id, request_id,
                       parent_run_id, pending_action_id, status
                FROM agent_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_agent_run_status(self, run_id: str, status: str) -> int:
        with get_connection(self.db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE agent_runs
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE run_id = ?
                """,
                (status, run_id),
            )
            connection.commit()
        return cursor.rowcount

    def insert_agent_trace(self, trace: dict[str, Any]) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO agent_traces (
                    trace_node_id, run_id, parent_run_id, session_id,
                    node_name, input_json, output_json, status, error_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _agent_trace_values(trace),
            )
            connection.commit()

    def list_agent_traces(self, run_id: str) -> list[dict[str, Any]]:
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT trace_node_id, run_id, parent_run_id, session_id,
                       node_name, input_json, output_json, status,
                       error_type, created_at
                FROM agent_traces
                WHERE run_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_policy_log(self, log: dict[str, Any]) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO policy_logs (
                    id, run_id, request_id, session_id, user_id, role,
                    tenant_id, action, tool_name, target_type, target_id,
                    decision, risk_level, reason, code, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _policy_log_values(log),
            )
            connection.commit()

    def list_policy_logs(self, run_id: str) -> list[dict[str, Any]]:
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT id, run_id, request_id, session_id, user_id, role,
                       tenant_id, action, tool_name, target_type, target_id,
                       decision, risk_level, reason, code, created_at
                FROM policy_logs
                WHERE run_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_failure_log(self, log: dict[str, Any]) -> None:
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO failure_logs (
                    id, run_id, session_id, failure_type, source,
                    retryable, retry_count, fallback_action, final_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _failure_log_values(log),
            )
            connection.commit()

    def list_failure_logs(self, run_id: str) -> list[dict[str, Any]]:
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT id, run_id, session_id, failure_type, source,
                       retryable, retry_count, fallback_action, final_status,
                       created_at
                FROM failure_logs
                WHERE run_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]


def _pending_action_values(pending_action: dict[str, Any]) -> tuple[Any, ...]:
    return (
        pending_action["pending_action_id"],
        pending_action["session_id"],
        pending_action["source_run_id"],
        pending_action["user_id"],
        pending_action["action_plan_json"],
        pending_action["risk_level"],
        pending_action["status"],
        pending_action["expires_at"],
        pending_action["created_at"],
        pending_action["updated_at"],
    )


def _pending_action_event_values(event: dict[str, Any]) -> tuple[Any, ...]:
    return (
        event["event_id"],
        event["pending_action_id"],
        event.get("run_id"),
        event.get("parent_run_id"),
        event.get("session_id"),
        event.get("user_id"),
        event.get("tenant_id"),
        event["event_type"],
        event.get("old_status"),
        event.get("new_status"),
        event.get("reason"),
        event["metadata_json"],
        event["created_at"],
    )


def _checkpoint_values(checkpoint: dict[str, Any]) -> tuple[Any, ...]:
    return (
        checkpoint["checkpoint_id"],
        checkpoint["run_id"],
        checkpoint.get("parent_run_id"),
        checkpoint["session_id"],
        checkpoint["user_id"],
        checkpoint["current_node"],
        checkpoint["checkpoint_type"],
        checkpoint["state_snapshot_json"],
        checkpoint["resume_policy_json"],
        checkpoint["status"],
        checkpoint["expires_at"],
        checkpoint["created_at"],
        checkpoint["updated_at"],
    )


def _checkpoint_event_values(event: dict[str, Any]) -> tuple[Any, ...]:
    return (
        event["event_id"],
        event["checkpoint_id"],
        event.get("run_id"),
        event.get("parent_run_id"),
        event.get("session_id"),
        event.get("user_id"),
        event["event_type"],
        event.get("old_status"),
        event.get("new_status"),
        event.get("reason"),
        event["metadata_json"],
        event["created_at"],
    )


def _resume_attempt_values(attempt: dict[str, Any]) -> tuple[Any, ...]:
    return (
        attempt["attempt_id"],
        attempt["checkpoint_id"],
        attempt.get("run_id"),
        attempt.get("parent_run_id"),
        attempt["session_id"],
        attempt["user_id"],
        attempt["status"],
        attempt.get("reason"),
        attempt["created_at"],
    )


def _tool_call_log_values(log: dict[str, Any]) -> tuple[Any, ...]:
    return (
        log["id"],
        log.get("tool_call_id"),
        log.get("idempotency_key"),
        log.get("action_fingerprint"),
        log["run_id"],
        log["session_id"],
        log["tool_name"],
        log["attempt_no"],
        log["tool_args_json"],
        log["tool_result_summary_json"],
        log["status"],
        log.get("failure_type"),
        log.get("latency_ms"),
    )


def _agent_trace_values(trace: dict[str, Any]) -> tuple[Any, ...]:
    return (
        trace["trace_node_id"],
        trace["run_id"],
        trace.get("parent_run_id"),
        trace["session_id"],
        trace["node_name"],
        trace["input_json"],
        trace["output_json"],
        trace["status"],
        trace.get("error_type"),
    )


def _policy_log_values(log: dict[str, Any]) -> tuple[Any, ...]:
    return (
        log["id"],
        log["run_id"],
        log.get("request_id"),
        log["session_id"],
        log["user_id"],
        log.get("role"),
        log.get("tenant_id"),
        log.get("action"),
        log.get("tool_name"),
        log.get("target_type"),
        log.get("target_id"),
        log["decision"],
        log["risk_level"],
        log.get("reason"),
        log.get("code"),
        log["created_at"],
    )


def _failure_log_values(log: dict[str, Any]) -> tuple[Any, ...]:
    return (
        log["id"],
        log["run_id"],
        log["session_id"],
        log["failure_type"],
        log["source"],
        log["retryable"],
        log["retry_count"],
        log.get("fallback_action"),
        log.get("final_status"),
    )
