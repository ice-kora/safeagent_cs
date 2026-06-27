import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.ids import generate_checkpoint_event_id, generate_checkpoint_id
from app.services.logging_service import LoggingService
from app.storage.runtime_store import get_runtime_store


class CheckpointError(ValueError):
    """Checkpoint 操作失败。"""


class CheckpointPermissionError(PermissionError):
    """Checkpoint 不属于当前用户或会话。"""


class CheckpointService:
    """可恢复执行点服务。

    该服务只保存/读取恢复点，不执行工具，不替代 PendingActionService。
    """

    STATUS_CREATED = "CREATED"
    STATUS_WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    STATUS_RESUMABLE = "RESUMABLE"
    STATUS_RESUMED = "RESUMED"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_FAILED = "FAILED"
    STATUS_COMPLETED = "COMPLETED"

    TYPE_WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    TYPE_EXECUTION_INTERRUPTED = "EXECUTION_INTERRUPTED"

    RESUMABLE_STATUSES = (
        STATUS_CREATED,
        STATUS_WAITING_CONFIRMATION,
        STATUS_RESUMABLE,
    )

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else None
        self.runtime_store = get_runtime_store(db_path=self.db_path)

    def create_checkpoint(
        self,
        *,
        run_id: str,
        session_id: str,
        user_id: str,
        current_node: str,
        checkpoint_type: str,
        state_snapshot: dict[str, Any],
        resume_policy: dict[str, Any],
        parent_run_id: str | None = None,
        status: str | None = None,
        ttl_minutes: int = 60,
    ) -> str:
        checkpoint_id = generate_checkpoint_id()
        now = self._now()
        checkpoint_status = status or self.STATUS_CREATED
        safe_snapshot = LoggingService.sanitize_payload(state_snapshot)
        safe_policy = LoggingService.sanitize_payload(resume_policy)
        self.runtime_store.insert_checkpoint(
            {
                "checkpoint_id": checkpoint_id,
                "run_id": run_id,
                "parent_run_id": parent_run_id,
                "session_id": session_id,
                "user_id": user_id,
                "current_node": current_node,
                "checkpoint_type": checkpoint_type,
                "state_snapshot_json": json.dumps(
                    safe_snapshot,
                    ensure_ascii=False,
                    default=str,
                ),
                "resume_policy_json": json.dumps(
                    safe_policy,
                    ensure_ascii=False,
                    default=str,
                ),
                "status": checkpoint_status,
                "expires_at": (now + timedelta(minutes=ttl_minutes)).isoformat(),
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
        )
        self.record_checkpoint_event(
            checkpoint_id=checkpoint_id,
            run_id=run_id,
            parent_run_id=parent_run_id,
            session_id=session_id,
            user_id=user_id,
            event_type="CREATED",
            old_status=None,
            new_status=checkpoint_status,
            reason="checkpoint created",
            metadata={
                "current_node": current_node,
                "checkpoint_type": checkpoint_type,
            },
        )
        return checkpoint_id

    def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        row = self.runtime_store.get_checkpoint(checkpoint_id)
        if not row:
            raise CheckpointError(f"checkpoint 不存在: {checkpoint_id}")
        return self._checkpoint_row_to_dict(row)

    def list_resumable_checkpoints(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.runtime_store.list_checkpoints(
            user_id=user_id,
            session_id=session_id,
            statuses=list(self.RESUMABLE_STATUSES),
        )
        checkpoints = [self._checkpoint_row_to_dict(row) for row in rows]
        return [item for item in checkpoints if not self._is_expired(item["expires_at"])]

    def validate_checkpoint_owner(
        self,
        checkpoint: dict[str, Any],
        *,
        user_id: str,
        session_id: str,
    ) -> None:
        if checkpoint["user_id"] != user_id:
            raise CheckpointPermissionError("checkpoint 不属于当前用户")
        if checkpoint["session_id"] != session_id:
            raise CheckpointPermissionError("checkpoint session 不匹配")

    def mark_resumed(
        self,
        checkpoint_id: str,
        *,
        run_id: str,
        parent_run_id: str | None,
        session_id: str,
        user_id: str,
    ) -> None:
        self._transition(
            checkpoint_id,
            self.STATUS_RESUMED,
            event_type="RESUMED",
            run_id=run_id,
            parent_run_id=parent_run_id,
            session_id=session_id,
            user_id=user_id,
            reason="checkpoint resumed",
        )

    def mark_expired(self, checkpoint_id: str, checkpoint: dict[str, Any]) -> None:
        self._transition(
            checkpoint_id,
            self.STATUS_EXPIRED,
            event_type="EXPIRED",
            run_id=None,
            parent_run_id=checkpoint.get("parent_run_id"),
            session_id=checkpoint["session_id"],
            user_id=checkpoint["user_id"],
            reason="checkpoint expired",
        )

    def cancel_checkpoint(
        self,
        checkpoint_id: str,
        *,
        user_id: str,
        session_id: str,
        reason: str = "checkpoint cancelled",
    ) -> dict[str, Any]:
        checkpoint = self.get_checkpoint(checkpoint_id)
        self.validate_checkpoint_owner(
            checkpoint,
            user_id=user_id,
            session_id=session_id,
        )
        if checkpoint["status"] not in self.RESUMABLE_STATUSES:
            raise CheckpointError(f"checkpoint 状态不可取消: {checkpoint['status']}")
        self._transition(
            checkpoint_id,
            self.STATUS_CANCELLED,
            event_type="CANCELLED",
            run_id=None,
            parent_run_id=checkpoint.get("parent_run_id"),
            session_id=session_id,
            user_id=user_id,
            reason=reason,
        )
        return self.get_checkpoint(checkpoint_id)

    def record_checkpoint_event(
        self,
        *,
        checkpoint_id: str,
        event_type: str,
        old_status: str | None,
        new_status: str | None,
        run_id: str | None = None,
        parent_run_id: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.runtime_store.insert_checkpoint_event(
            {
                "event_id": generate_checkpoint_event_id(),
                "checkpoint_id": checkpoint_id,
                "run_id": run_id,
                "parent_run_id": parent_run_id,
                "session_id": session_id,
                "user_id": user_id,
                "event_type": event_type,
                "old_status": old_status,
                "new_status": new_status,
                "reason": reason,
                "metadata_json": json.dumps(
                    LoggingService.sanitize_payload(metadata or {}),
                    ensure_ascii=False,
                    default=str,
                ),
                "created_at": self._now().isoformat(),
            }
        )

    def list_checkpoint_events(self, checkpoint_id: str) -> list[dict[str, Any]]:
        rows = self.runtime_store.list_checkpoint_events(checkpoint_id)
        events: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            events.append(LoggingService.sanitize_payload(item))
        return events

    def _transition(
        self,
        checkpoint_id: str,
        status: str,
        *,
        event_type: str,
        run_id: str | None,
        parent_run_id: str | None,
        session_id: str,
        user_id: str,
        reason: str,
    ) -> None:
        current = self.get_checkpoint(checkpoint_id)
        updated_rows = self.runtime_store.update_checkpoint_status(
            checkpoint_id=checkpoint_id,
            status=status,
            updated_at=self._now().isoformat(),
        )
        if updated_rows == 0:
            raise CheckpointError(f"checkpoint 不存在: {checkpoint_id}")
        self.record_checkpoint_event(
            checkpoint_id=checkpoint_id,
            run_id=run_id,
            parent_run_id=parent_run_id,
            session_id=session_id,
            user_id=user_id,
            event_type=event_type,
            old_status=current["status"],
            new_status=status,
            reason=reason,
            metadata={},
        )

    def _checkpoint_row_to_dict(self, row: dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        item["state_snapshot"] = json.loads(item.pop("state_snapshot_json") or "{}")
        item["resume_policy"] = json.loads(item.pop("resume_policy_json") or "{}")
        item["events"] = self.list_checkpoint_events(item["checkpoint_id"])
        return LoggingService.sanitize_payload(item)

    @staticmethod
    def _is_expired(expires_at: str) -> bool:
        expires_at_datetime = datetime.fromisoformat(expires_at)
        if expires_at_datetime.tzinfo is None:
            expires_at_datetime = expires_at_datetime.replace(tzinfo=timezone.utc)
        return expires_at_datetime <= CheckpointService._now()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
