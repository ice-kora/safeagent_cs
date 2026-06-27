from pathlib import Path
from typing import Any

from app.core.ids import generate_ticket_id
from app.core.tool_result import ToolResult
from app.services.logging_service import LoggingService
from app.storage.runtime_store import get_runtime_store


OPEN_TICKET_STATUSES = {"OPEN", "PROCESSING"}
TICKET_ARGS_INVALID = "TICKET_ARGS_INVALID"


def create_ticket(
    user_id: str,
    action: str,
    target_type: str,
    target_id: str | None,
    ticket_type: str,
    risk_level: str = "L4",
    description: str | None = None,
    db_path: str | Path | None = None,
    source_run_id: str | None = None,
    parent_run_id: str | None = None,
    pending_action_id: str | None = None,
) -> ToolResult:
    """创建人工处理工单，并对未关闭工单做幂等控制。

    P0 的工单工具只写本地 SQLite，不接真实客服平台。幂等键沿用架构约定：
    user_id + action + target_type + target_id；如果已有 OPEN / PROCESSING 工单，
    直接返回已有工单，避免重复创建。
    """
    invalid_result = _validate_ticket_args(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ticket_type=ticket_type,
    )
    if invalid_result:
        return invalid_result

    runtime_store = get_runtime_store(db_path=db_path)
    idempotency_key = _build_idempotency_key(user_id, action, target_type, target_id)
    safe_description = _sanitize_description(description)

    existing_ticket = runtime_store.get_open_ticket_by_idempotency_key(idempotency_key)
    if existing_ticket:
        data = _ticket_row_to_data(existing_ticket, created=False)
        summary = f"已存在未关闭工单 {data['ticket_id']}，本次不重复创建。"
        return ToolResult(
            success=True,
            tool_name="ticket_tool.create_ticket",
            data=data,
            summary=summary,
            safe_for_llm=True,
        )

    ticket_id = generate_ticket_id()
    runtime_store.insert_ticket(
        {
            "id": ticket_id,
            "user_id": user_id,
            "type": ticket_type,
            "status": "OPEN",
            "risk_level": risk_level,
            "idempotency_key": idempotency_key,
            "source_run_id": source_run_id,
            "parent_run_id": parent_run_id,
            "pending_action_id": pending_action_id,
            "description": safe_description,
        }
    )

    summary = f"已创建人工处理工单 {ticket_id}。"
    return ToolResult(
        success=True,
        tool_name="ticket_tool.create_ticket",
        data={
            "ticket_id": ticket_id,
            "status": "OPEN",
            "ticket_type": ticket_type,
            "risk_level": risk_level,
            "created": True,
        },
        summary=summary,
        safe_for_llm=True,
    )


def _validate_ticket_args(
    user_id: str,
    action: str,
    target_type: str,
    target_id: str | None,
    ticket_type: str,
) -> ToolResult | None:
    """校验创建工单所需的最小系统上下文。

    工单幂等键依赖 user_id / action / target_type / target_id。缺少这些字段
    会让不同请求互相串扰，所以必须在写库前拒绝。
    """
    normalized_user_id = user_id.strip() if user_id else ""
    normalized_action = action.strip() if action else ""
    normalized_target_type = target_type.strip() if target_type else ""
    normalized_target_id = target_id.strip() if target_id else ""
    normalized_ticket_type = ticket_type.strip() if ticket_type else ""

    requires_target_id = (
        normalized_target_type == "order"
        or normalized_ticket_type == "refund"
        or normalized_action == "request_refund"
    )
    if (
        not normalized_user_id
        or not normalized_action
        or not normalized_target_type
        or (requires_target_id and not normalized_target_id)
    ):
        return ToolResult(
            success=False,
            tool_name="ticket_tool.create_ticket",
            data={},
            summary="创建工单缺少必要参数。",
            error_type=TICKET_ARGS_INVALID,
            safe_for_llm=True,
        )
    return None


def _build_idempotency_key(
    user_id: str,
    action: str,
    target_type: str,
    target_id: str | None,
) -> str:
    return f"{user_id}:{action}:{target_type}:{target_id}"


def _sanitize_description(description: str | None) -> str | None:
    if description is None:
        return None
    sanitized = LoggingService.sanitize_payload({"description": description})
    return sanitized["description"]


def _ticket_row_to_data(row: Any, created: bool) -> dict[str, Any]:
    return {
        "ticket_id": row["id"],
        "status": row["status"],
        "ticket_type": row["type"],
        "risk_level": row["risk_level"],
        "created": created,
    }
