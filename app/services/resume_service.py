from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.action_plan_validator import ActionPlanValidator
from app.core.constants import PolicyDecisionType
from app.core.ids import generate_request_id, generate_resume_attempt_id
from app.services.checkpoint_service import (
    CheckpointError,
    CheckpointPermissionError,
    CheckpointService,
)
from app.services.pending_action_service import (
    PendingActionError,
    PendingActionPermissionError,
    PendingActionService,
)
from app.services.policy_service import (
    PolicyAuditContext,
    PolicyService,
    evaluate_policy,
)
from app.services.trace_service import TraceService
from app.storage.runtime_store import get_runtime_store


class ResumeError(ValueError):
    """恢复失败。"""


class ResumeService:
    """最小恢复服务。

    resume 只恢复到安全的“可继续确认”状态，不直接执行工具。
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        checkpoint_service: CheckpointService | None = None,
        pending_action_service: PendingActionService | None = None,
        trace_service: TraceService | None = None,
        action_plan_validator: ActionPlanValidator | None = None,
        policy_service: PolicyService | None = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path else None
        self.runtime_store = get_runtime_store(db_path=self.db_path)
        self.checkpoint_service = checkpoint_service or CheckpointService(
            db_path=self.db_path
        )
        self.pending_action_service = pending_action_service or PendingActionService(
            db_path=self.db_path
        )
        self.trace_service = trace_service or TraceService(db_path=self.db_path)
        self.action_plan_validator = action_plan_validator or ActionPlanValidator()
        self.policy_service = policy_service or PolicyService()

    def resume_from_checkpoint(
        self,
        *,
        checkpoint_id: str,
        user_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        checkpoint = self.checkpoint_service.get_checkpoint(checkpoint_id)
        self._validate_resume_request(checkpoint, user_id=user_id, session_id=session_id)
        pending_action_id = checkpoint["state_snapshot"].get("pending_action_id")
        if not isinstance(pending_action_id, str) or not pending_action_id:
            raise ResumeError("checkpoint 缺少 pending_action_id")

        request_id = generate_request_id()
        parent_run_id = checkpoint["run_id"]
        run_id = self.trace_service.start_run(
            session_id=session_id,
            user_id=user_id,
            request_id=request_id,
            parent_run_id=parent_run_id,
            pending_action_id=pending_action_id,
        )
        try:
            pending_action = self.pending_action_service.validate_pending_action(
                pending_action_id=pending_action_id,
                user_id=user_id,
            )
            if pending_action["session_id"] != session_id:
                raise ResumeError("pending_action session 不匹配")
            action_plan = pending_action["action_plan"]
            validation_result = self.action_plan_validator.validate(action_plan)
            self.trace_service.append_trace(
                run_id=run_id,
                node_name="resume_action_plan_validation",
                input_json={"action_plan": action_plan.to_dict()},
                output_json={
                    "status": validation_result.status.value,
                    "reason": validation_result.reason,
                },
                status="SUCCESS" if validation_result.is_valid else "FAILED",
                error_type=None
                if validation_result.is_valid
                else validation_result.status.value,
            )
            if not validation_result.is_valid:
                raise ResumeError("checkpoint action_plan 校验失败")

            policy_decision = evaluate_policy(
                self.policy_service,
                action_plan,
                customer_user_id=user_id,
                audit_context=PolicyAuditContext(
                    run_id=run_id,
                    request_id=request_id,
                    session_id=session_id,
                    user_id=user_id,
                ),
            )
            self.trace_service.append_trace(
                run_id=run_id,
                node_name="resume_policy_review",
                input_json={"action_plan": action_plan.to_dict(), "user_id": user_id},
                output_json=policy_decision.to_dict(),
            )
            if policy_decision.decision not in {
                PolicyDecisionType.ALLOW,
                PolicyDecisionType.CONFIRM_REQUIRED,
            }:
                self.trace_service.finish_run(run_id)
                self._record_attempt(
                    checkpoint_id=checkpoint_id,
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                    session_id=session_id,
                    user_id=user_id,
                    status="FAILED",
                    reason=policy_decision.decision.value,
                )
                return {
                    "request_id": request_id,
                    "run_id": run_id,
                    "parent_run_id": parent_run_id,
                    "checkpoint_id": checkpoint_id,
                    "pending_action_id": pending_action_id,
                    "status": policy_decision.decision.value,
                    "policy_decision": policy_decision.to_dict(),
                    "message": "恢复时策略复核未通过，未执行工具",
                }

            self.trace_service.append_trace(
                run_id=run_id,
                node_name="checkpoint_resume_ready",
                input_json={"checkpoint_id": checkpoint_id},
                output_json={
                    "pending_action_id": pending_action_id,
                    "next_api": "/api/confirm",
                    "tool_execution": "not_executed",
                },
            )
            self.trace_service.finish_run(run_id)
            self.checkpoint_service.mark_resumed(
                checkpoint_id,
                run_id=run_id,
                parent_run_id=parent_run_id,
                session_id=session_id,
                user_id=user_id,
            )
            self._record_attempt(
                checkpoint_id=checkpoint_id,
                run_id=run_id,
                parent_run_id=parent_run_id,
                session_id=session_id,
                user_id=user_id,
                status="SUCCESS",
                reason="RESUME_READY",
            )
            return {
                "request_id": request_id,
                "run_id": run_id,
                "parent_run_id": parent_run_id,
                "checkpoint_id": checkpoint_id,
                "pending_action_id": pending_action_id,
                "status": "RESUME_READY",
                "policy_decision": policy_decision.to_dict(),
                "message": "已恢复到待确认状态，请继续确认或取消",
            }
        except Exception as exc:
            self.trace_service.fail_run(run_id, exc.__class__.__name__)
            self._record_attempt(
                checkpoint_id=checkpoint_id,
                run_id=run_id,
                parent_run_id=parent_run_id,
                session_id=session_id,
                user_id=user_id,
                status="FAILED",
                reason=str(exc)[:160],
            )
            raise

    def cancel_checkpoint(
        self,
        *,
        checkpoint_id: str,
        user_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        checkpoint = self.checkpoint_service.cancel_checkpoint(
            checkpoint_id,
            user_id=user_id,
            session_id=session_id,
        )
        pending_action_id = checkpoint["state_snapshot"].get("pending_action_id")
        if isinstance(pending_action_id, str) and pending_action_id:
            try:
                self.pending_action_service.mark_cancelled(
                    pending_action_id,
                    reason="checkpoint cancelled",
                )
            except PendingActionError:
                pass
        return checkpoint

    def _validate_resume_request(
        self,
        checkpoint: dict[str, Any],
        *,
        user_id: str,
        session_id: str,
    ) -> None:
        self.checkpoint_service.validate_checkpoint_owner(
            checkpoint,
            user_id=user_id,
            session_id=session_id,
        )
        if checkpoint["status"] not in CheckpointService.RESUMABLE_STATUSES:
            raise ResumeError(f"checkpoint 状态不可恢复: {checkpoint['status']}")
        expires_at = datetime.fromisoformat(checkpoint["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            self.checkpoint_service.mark_expired(
                checkpoint["checkpoint_id"],
                checkpoint,
            )
            raise ResumeError("checkpoint 已过期")

    def _record_attempt(
        self,
        *,
        checkpoint_id: str,
        run_id: str | None,
        parent_run_id: str | None,
        session_id: str,
        user_id: str,
        status: str,
        reason: str | None,
    ) -> None:
        self.runtime_store.insert_resume_attempt(
            {
                "attempt_id": generate_resume_attempt_id(),
                "checkpoint_id": checkpoint_id,
                "run_id": run_id,
                "parent_run_id": parent_run_id,
                "session_id": session_id,
                "user_id": user_id,
                "status": status,
                "reason": reason,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
