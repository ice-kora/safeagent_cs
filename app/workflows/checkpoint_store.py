from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.workflows.checkpoint_policy import (
    CheckpointNodeRisk,
    CheckpointResumeDecision,
    can_resume_from_snapshot,
    classify_checkpoint_node,
)
from app.workflows.langgraph_state_schema import state_to_json_safe_dict
from app.workflows.safeagent_state import SafeAgentWorkflowState


@dataclass(frozen=True)
class CheckpointRecord:
    """内存 checkpoint 记录。

    该结构只用于 readiness 测试，不是生产持久化实现。
    """

    checkpoint_id: str
    request_id: str
    run_id: str
    node_name: str
    snapshot: dict[str, Any]
    created_at: str
    route: str | None = None


@dataclass(frozen=True)
class ResumeDryRunResult:
    """resume dry-run 结果，不执行任何恢复动作。"""

    checkpoint_id: str
    next_node: str
    decision: CheckpointResumeDecision
    snapshot_summary: dict[str, Any]


class InMemoryCheckpointStore:
    """内存 checkpoint store。

    只负责保存/查询 JSON-safe snapshot 和执行 dry-run 判断，不调用
    ToolGateway，不创建 pending_action，不修改业务数据库。
    """

    def __init__(self) -> None:
        self._records: dict[str, CheckpointRecord] = {}

    def save_state_checkpoint(
        self,
        *,
        state: SafeAgentWorkflowState,
        node_name: str,
        route: str | None = None,
    ) -> CheckpointRecord:
        checkpoint_id = f"ckpt_{uuid4().hex}"
        snapshot = state_to_json_safe_dict(state, route=route)
        record = CheckpointRecord(
            checkpoint_id=checkpoint_id,
            request_id=state.request_id,
            run_id=state.run_id,
            node_name=node_name,
            snapshot=deepcopy(snapshot),
            created_at=datetime.now(timezone.utc).isoformat(),
            route=route,
        )
        self._records[checkpoint_id] = record
        return record

    def get_checkpoint(self, checkpoint_id: str) -> CheckpointRecord | None:
        record = self._records.get(checkpoint_id)
        return _copy_record(record) if record else None

    def list_checkpoints_for_run(self, run_id: str) -> list[CheckpointRecord]:
        records = [
            record
            for record in self._records.values()
            if record.run_id == run_id
        ]
        return [_copy_record(record) for record in records]

    def dry_run_resume(
        self,
        *,
        checkpoint_id: str,
        next_node: str,
    ) -> ResumeDryRunResult:
        record = self._records.get(checkpoint_id)
        if record is None:
            risk = classify_checkpoint_node(next_node)
            decision = CheckpointResumeDecision(
                allowed=False,
                reason="checkpoint_id 不存在",
                node_name=next_node,
                risk=(
                    risk
                    if risk != CheckpointNodeRisk.UNSAFE_TO_RESUME
                    else CheckpointNodeRisk.UNSAFE_TO_RESUME
                ),
            )
            return ResumeDryRunResult(
                checkpoint_id=checkpoint_id,
                next_node=next_node,
                decision=decision,
                snapshot_summary={},
            )

        snapshot = deepcopy(record.snapshot)
        decision = can_resume_from_snapshot(snapshot, next_node)
        return ResumeDryRunResult(
            checkpoint_id=checkpoint_id,
            next_node=next_node,
            decision=decision,
            snapshot_summary=_build_snapshot_summary(snapshot),
        )


def _copy_record(record: CheckpointRecord) -> CheckpointRecord:
    return CheckpointRecord(
        checkpoint_id=record.checkpoint_id,
        request_id=record.request_id,
        run_id=record.run_id,
        node_name=record.node_name,
        snapshot=deepcopy(record.snapshot),
        created_at=record.created_at,
        route=record.route,
    )


def _build_snapshot_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    action_plan = snapshot.get("action_plan") or {}
    policy_decision = snapshot.get("policy_decision") or {}
    return {
        "request_id": snapshot.get("request_id"),
        "run_id": snapshot.get("run_id"),
        "final_status": snapshot.get("final_status"),
        "route": snapshot.get("route"),
        "action": action_plan.get("action"),
        "policy_decision": policy_decision.get("decision"),
        "has_tool_result": bool(snapshot.get("tool_result")),
        "has_pending_action": bool(snapshot.get("pending_action_id")),
        "schema_version": snapshot.get("schema_version"),
    }
