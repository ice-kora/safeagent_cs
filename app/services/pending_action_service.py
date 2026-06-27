import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.action_plan import ActionPlan
from app.core.ids import generate_pending_action_id
from app.services.pending_action_event_service import PendingActionEventService
from app.storage.runtime_store import get_runtime_store


class PendingActionError(ValueError):
    """待确认动作校验失败。"""


class PendingActionPermissionError(PermissionError):
    """待确认动作不属于当前用户。"""


class PendingActionService:
    """二次确认待执行动作服务。

    PendingActionService 只负责保存、读取和更新需要用户确认的 ActionPlan。
    它不创建 run_id,不调用 ToolGateway,不判断权限,也不执行业务动作；
    后续 /api/confirm 或 Workflow 会在确认后重新复核策略并执行工具调用。
    """

    STATUS_PENDING = "PENDING"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_EXECUTED = "EXECUTED"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_CANCELLED = "CANCELLED"

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else None
        self.runtime_store = get_runtime_store(db_path=self.db_path)
        self.event_service = PendingActionEventService(db_path=self.db_path)

    def create_pending_action(
        self,
        session_id: str,
        source_run_id: str,
        user_id: str,
        action_plan: ActionPlan,
        risk_level: str,
        ttl_minutes: int = 10,
    ) -> str:
        """创建待确认动作，并将 ActionPlan 结构化写入 SQLite。

        P0 默认 10 分钟过期。这里保存的是候选计划快照，确认时仍需要由
        /api/confirm 或 Workflow 再次复核 PolicyService，不能直接执行。
        """
        pending_action_id = generate_pending_action_id()
        now = self._now()
        expires_at = now + timedelta(minutes=ttl_minutes)
        action_plan_json = json.dumps(
            action_plan.to_dict(),
            ensure_ascii=False,
            default=str,
        )

        self.runtime_store.create_pending_action(
            {
                "pending_action_id": pending_action_id,
                "session_id": session_id,
                "source_run_id": source_run_id,
                "user_id": user_id,
                "action_plan_json": action_plan_json,
                "risk_level": risk_level,
                "status": self.STATUS_PENDING,
                "expires_at": expires_at.isoformat(),
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
        )
        self.event_service.record_event(
            pending_action_id=pending_action_id,
            run_id=source_run_id,
            session_id=session_id,
            user_id=user_id,
            event_type=PendingActionEventService.EVENT_CREATED,
            old_status=None,
            new_status=self.STATUS_PENDING,
            reason="pending_action created",
            metadata={
                "risk_level": risk_level,
                "action": action_plan.action,
                "target_type": action_plan.target_type,
                "target_id": action_plan.target_id,
            },
        )
        return pending_action_id

    def get_pending_action(self, pending_action_id: str) -> dict[str, Any] | None:
        """按 ID 读取待确认动作原始记录。"""
        return self.runtime_store.get_pending_action(pending_action_id)

    def validate_pending_action(
        self,
        pending_action_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        """校验待确认动作是否仍可确认。

        合法时返回反序列化后的 ActionPlan 和必要上下文字段；非法时抛出清晰
        异常。过期的 PENDING 记录会先标记为 EXPIRED，再拒绝继续确认。
        """
        record = self.get_pending_action(pending_action_id)
        if record is None:
            raise PendingActionError(f"pending_action 不存在: {pending_action_id}")

        if record["user_id"] != user_id:
            raise PendingActionPermissionError(
                f"pending_action 不属于当前用户: {pending_action_id}"
            )

        status = record["status"]
        if status != self.STATUS_PENDING:
            raise PendingActionError(
                f"pending_action 状态不是 PENDING: {pending_action_id}, status={status}"
            )

        if self._is_expired(record["expires_at"]):
            self.mark_expired(pending_action_id)
            raise PendingActionError(f"pending_action 已过期: {pending_action_id}")

        return {
            "pending_action_id": record["pending_action_id"],
            "session_id": record["session_id"],
            "source_run_id": record["source_run_id"],
            "user_id": record["user_id"],
            "risk_level": record["risk_level"],
            "status": record["status"],
            "expires_at": record["expires_at"],
            "action_plan": self._deserialize_action_plan(record["action_plan_json"]),
        }

    def mark_confirmed(
        self,
        pending_action_id: str,
        run_id: str | None = None,
        parent_run_id: str | None = None,
        tenant_id: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._update_status(
            pending_action_id,
            self.STATUS_CONFIRMED,
            event_type=PendingActionEventService.EVENT_CONFIRMED,
            run_id=run_id,
            parent_run_id=parent_run_id,
            tenant_id=tenant_id,
            reason=reason or "pending_action confirmed",
            metadata=metadata,
        )

    def mark_executed(
        self,
        pending_action_id: str,
        run_id: str | None = None,
        parent_run_id: str | None = None,
        tenant_id: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._update_status(
            pending_action_id,
            self.STATUS_EXECUTED,
            event_type=PendingActionEventService.EVENT_EXECUTED,
            run_id=run_id,
            parent_run_id=parent_run_id,
            tenant_id=tenant_id,
            reason=reason or "pending_action executed",
            metadata=metadata,
        )

    def mark_expired(
        self,
        pending_action_id: str,
        run_id: str | None = None,
        parent_run_id: str | None = None,
        tenant_id: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._update_status(
            pending_action_id,
            self.STATUS_EXPIRED,
            event_type=PendingActionEventService.EVENT_EXPIRED,
            run_id=run_id,
            parent_run_id=parent_run_id,
            tenant_id=tenant_id,
            reason=reason or "pending_action expired",
            metadata=metadata,
        )

    def mark_cancelled(
        self,
        pending_action_id: str,
        run_id: str | None = None,
        parent_run_id: str | None = None,
        tenant_id: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._update_status(
            pending_action_id,
            self.STATUS_CANCELLED,
            event_type=PendingActionEventService.EVENT_CANCELLED,
            run_id=run_id,
            parent_run_id=parent_run_id,
            tenant_id=tenant_id,
            reason=reason or "pending_action cancelled",
            metadata=metadata,
        )

    def _update_status(
        self,
        pending_action_id: str,
        status: str,
        event_type: str,
        run_id: str | None = None,
        parent_run_id: str | None = None,
        tenant_id: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        row = self.runtime_store.get_pending_action_status_context(pending_action_id)
        if not row:
            raise PendingActionError(f"pending_action 不存在: {pending_action_id}")
        updated_rows = self.runtime_store.update_pending_action_status(
            pending_action_id=pending_action_id,
            status=status,
            updated_at=self._now().isoformat(),
        )
        if updated_rows == 0:
            raise PendingActionError(f"pending_action 不存在: {pending_action_id}")
        old_status = row["status"]
        self.event_service.record_event(
            pending_action_id=pending_action_id,
            run_id=run_id,
            parent_run_id=parent_run_id,
            session_id=row["session_id"],
            user_id=row["user_id"],
            tenant_id=tenant_id,
            event_type=event_type,
            old_status=old_status,
            new_status=status,
            reason=reason,
            metadata={
                "source_run_id": row["source_run_id"],
                **(metadata or {}),
            },
        )

    @staticmethod
    def _deserialize_action_plan(action_plan_json: str) -> ActionPlan:
        data = json.loads(action_plan_json)
        return ActionPlan(
            intent=data["intent"],
            action=data["action"],
            target_type=data.get("target_type"),
            target_id=data.get("target_id"),
            tool_name=data.get("tool_name"),
            tool_args=data.get("tool_args") or {},
            reason=data.get("reason", ""),
        )

    @staticmethod
    def _is_expired(expires_at: str) -> bool:
        expires_at_datetime = datetime.fromisoformat(expires_at)
        if expires_at_datetime.tzinfo is None:
            expires_at_datetime = expires_at_datetime.replace(tzinfo=timezone.utc)
        return expires_at_datetime <= PendingActionService._now()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
