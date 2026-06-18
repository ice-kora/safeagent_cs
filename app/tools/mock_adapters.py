from pathlib import Path
from typing import Any

from app.core.tool_result import ToolError, ToolResult
from app.tools import knowledge_tool, order_tool, ticket_tool
from app.tools.adapter import ToolCapability, ToolRequest


def _metadata_path(metadata: dict[str, Any] | None, key: str) -> Path | None:
    value = (metadata or {}).get(key)
    return Path(value) if value else None


def _missing_idempotency_result(tool_name: str) -> ToolResult:
    return ToolResult(
        success=False,
        tool_name=tool_name,
        data={},
        summary="副作用工具缺少幂等键，已拒绝执行。",
        error_type="IDEMPOTENCY_KEY_REQUIRED",
        safe_for_llm=True,
        error=ToolError(
            failure_type="IDEMPOTENCY_KEY_REQUIRED",
            message="side-effect tool requires idempotency_key",
            retryable=False,
        ),
    )


class KnowledgeToolAdapter:
    name = "knowledge_tool.query_policy"
    capability = ToolCapability(
        tool_name=name,
        read_only=True,
        side_effect=False,
        requires_idempotency=False,
        safe_for_llm=True,
    )

    def execute(self, request: ToolRequest) -> ToolResult:
        return knowledge_tool.query_policy(query=str(request.tool_args.get("query", "")))


class OrderQueryAdapter:
    name = "order_tool.query_order"
    capability = ToolCapability(
        tool_name=name,
        read_only=True,
        side_effect=False,
        requires_idempotency=False,
        safe_for_llm=True,
    )

    def execute(self, request: ToolRequest) -> ToolResult:
        metadata = request.context.metadata
        return order_tool.query_order(
            order_id=str(request.tool_args.get("order_id", "")),
            mock_dir=_metadata_path(metadata, "mock_dir"),
            db_path=_metadata_path(metadata, "db_path"),
        )


class OrderChangeAddressAdapter:
    name = "order_tool.change_address"
    capability = ToolCapability(
        tool_name=name,
        read_only=False,
        side_effect=True,
        requires_idempotency=True,
        safe_for_llm=True,
    )

    def execute(self, request: ToolRequest) -> ToolResult:
        if not request.context.idempotency_key:
            return _missing_idempotency_result(self.name)
        metadata = request.context.metadata
        return order_tool.change_address(
            order_id=str(request.tool_args.get("order_id", "")),
            new_address=request.tool_args.get("new_address"),
            mock_dir=_metadata_path(metadata, "mock_dir"),
            db_path=_metadata_path(metadata, "db_path"),
        )


class TicketCreateAdapter:
    name = "ticket_tool.create_ticket"
    capability = ToolCapability(
        tool_name=name,
        read_only=False,
        side_effect=True,
        requires_idempotency=True,
        safe_for_llm=True,
    )

    def execute(self, request: ToolRequest) -> ToolResult:
        if not request.context.idempotency_key:
            return _missing_idempotency_result(self.name)
        metadata = request.context.metadata
        tool_args = request.tool_args
        return ticket_tool.create_ticket(
            user_id=str(tool_args.get("user_id", "")),
            action=str(tool_args.get("action", "")),
            target_type=str(tool_args.get("target_type", "")),
            target_id=tool_args.get("target_id"),
            ticket_type=str(tool_args.get("ticket_type", "general")),
            risk_level=str(tool_args.get("risk_level", "L4")),
            description=tool_args.get("description"),
            db_path=_metadata_path(metadata, "db_path"),
            source_run_id=tool_args.get("source_run_id"),
            parent_run_id=tool_args.get("parent_run_id"),
            pending_action_id=tool_args.get("pending_action_id"),
        )
