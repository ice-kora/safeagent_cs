from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.logging_service import LoggingService
from app.storage.runtime_store import get_runtime_store


@dataclass(frozen=True)
class PendingActionEvent:
    """pending_action 状态流转事件。"""

    event_id: str
    pending_action_id: str
    run_id: str | None
    parent_run_id: str | None
    session_id: str | None
    user_id: str | None
    tenant_id: str | None
    event_type: str
    old_status: str | None
    new_status: str | None
    reason: str | None
    metadata: dict[str, Any]
    created_at: str


class PendingActionEventService:
    """pending_action 事件事实源服务。

    状态表只描述当前状态，事件表负责解释状态如何变化。这里不改变
    PendingActionService 的状态机，只在状态变化后追加脱敏事件。
    """

    EVENT_CREATED = "CREATED"
    EVENT_CONFIRMED = "CONFIRMED"
    EVENT_CANCELLED = "CANCELLED"
    EVENT_EXPIRED = "EXPIRED"
    EVENT_EXECUTED = "EXECUTED"
    EVENT_POLICY_RECHECK_FAILED = "POLICY_RECHECK_FAILED"

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else None
        self.runtime_store = get_runtime_store(db_path=self.db_path)

    def record_event(
        self,
        *,
        pending_action_id: str,
        event_type: str,
        old_status: str | None = None,
        new_status: str | None = None,
        run_id: str | None = None,
        parent_run_id: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PendingActionEvent:
        created_at = datetime.now(timezone.utc).isoformat()
        safe_metadata = LoggingService.sanitize_payload(metadata or {})
        safe_reason = LoggingService.sanitize_payload(reason)
        event = PendingActionEvent(
            event_id=self._generate_event_id(),
            pending_action_id=pending_action_id,
            run_id=run_id,
            parent_run_id=parent_run_id,
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            event_type=event_type,
            old_status=old_status,
            new_status=new_status,
            reason=safe_reason,
            metadata=safe_metadata,
            created_at=created_at,
        )
        self.runtime_store.insert_pending_action_event(
            {
                "event_id": event.event_id,
                "pending_action_id": event.pending_action_id,
                "run_id": event.run_id,
                "parent_run_id": event.parent_run_id,
                "session_id": event.session_id,
                "user_id": event.user_id,
                "tenant_id": event.tenant_id,
                "event_type": event.event_type,
                "old_status": event.old_status,
                "new_status": event.new_status,
                "reason": event.reason,
                "metadata_json": json.dumps(
                    event.metadata,
                    ensure_ascii=False,
                    default=str,
                ),
                "created_at": event.created_at,
            }
        )
        return event

    def list_events(self, pending_action_id: str) -> list[PendingActionEvent]:
        rows = self.runtime_store.list_pending_action_events(pending_action_id)
        return [self._row_to_event(row) for row in rows]

    @staticmethod
    def _row_to_event(row: Any) -> PendingActionEvent:
        return PendingActionEvent(
            event_id=row["event_id"],
            pending_action_id=row["pending_action_id"],
            run_id=row["run_id"],
            parent_run_id=row["parent_run_id"],
            session_id=row["session_id"],
            user_id=row["user_id"],
            tenant_id=row["tenant_id"],
            event_type=row["event_type"],
            old_status=row["old_status"],
            new_status=row["new_status"],
            reason=row["reason"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            created_at=row["created_at"],
        )

    @staticmethod
    def _generate_event_id() -> str:
        return f"pae_{uuid4().hex[:16]}"
