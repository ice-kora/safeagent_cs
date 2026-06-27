from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from app.storage.runtime_config import (
    RUNTIME_BACKEND_POSTGRES,
    RUNTIME_BACKEND_SQLITE,
    get_runtime_database_settings,
)


class RuntimeStore(Protocol):
    """运行时数据 Store 协议。

    业务服务只依赖这个协议，不直接关心 SQLite / PostgreSQL 的 SQL 细节。
    """

    backend: str

    def init_schema(self) -> None: ...

    def get_open_ticket_by_idempotency_key(
        self, idempotency_key: str
    ) -> dict[str, Any] | None: ...

    def insert_ticket(self, ticket: dict[str, Any]) -> None: ...

    def create_pending_action(self, pending_action: dict[str, Any]) -> None: ...

    def get_pending_action(self, pending_action_id: str) -> dict[str, Any] | None: ...

    def get_pending_action_status_context(
        self, pending_action_id: str
    ) -> dict[str, Any] | None: ...

    def update_pending_action_status(
        self,
        pending_action_id: str,
        status: str,
        updated_at: str,
    ) -> int: ...

    def insert_pending_action_event(self, event: dict[str, Any]) -> None: ...

    def list_pending_action_events(
        self, pending_action_id: str
    ) -> list[dict[str, Any]]: ...

    def list_pending_actions(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def insert_checkpoint(self, checkpoint: dict[str, Any]) -> None: ...

    def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any] | None: ...

    def list_checkpoints(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        statuses: list[str] | None = None,
    ) -> list[dict[str, Any]]: ...

    def update_checkpoint_status(
        self,
        checkpoint_id: str,
        status: str,
        updated_at: str,
    ) -> int: ...

    def insert_checkpoint_event(self, event: dict[str, Any]) -> None: ...

    def list_checkpoint_events(self, checkpoint_id: str) -> list[dict[str, Any]]: ...

    def insert_resume_attempt(self, attempt: dict[str, Any]) -> None: ...

    def insert_tool_call_log(self, log: dict[str, Any]) -> None: ...

    def list_tool_call_logs(self, run_id: str) -> list[dict[str, Any]]: ...

    def insert_agent_run(self, run: dict[str, Any]) -> None: ...

    def get_agent_run(self, run_id: str) -> dict[str, Any] | None: ...

    def update_agent_run_status(self, run_id: str, status: str) -> int: ...

    def insert_agent_trace(self, trace: dict[str, Any]) -> None: ...

    def list_agent_traces(self, run_id: str) -> list[dict[str, Any]]: ...

    def insert_policy_log(self, log: dict[str, Any]) -> None: ...

    def list_policy_logs(self, run_id: str) -> list[dict[str, Any]]: ...

    def insert_failure_log(self, log: dict[str, Any]) -> None: ...

    def list_failure_logs(self, run_id: str) -> list[dict[str, Any]]: ...


def get_runtime_store(
    *,
    db_path: str | Path | None = None,
    backend: str | None = None,
    database_url: str | None = None,
) -> RuntimeStore:
    settings = get_runtime_database_settings()
    selected_backend = (backend or settings.backend).strip().lower()
    if selected_backend not in {RUNTIME_BACKEND_SQLITE, RUNTIME_BACKEND_POSTGRES}:
        selected_backend = RUNTIME_BACKEND_SQLITE

    if db_path is not None and backend is None:
        selected_backend = RUNTIME_BACKEND_SQLITE

    if selected_backend == RUNTIME_BACKEND_POSTGRES:
        from app.storage.runtime_postgres import PostgresRuntimeStore

        return PostgresRuntimeStore(database_url=database_url or settings.database_url)

    from app.storage.runtime_sqlite import SQLiteRuntimeStore

    return SQLiteRuntimeStore(db_path=db_path)
