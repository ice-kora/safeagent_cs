import json
import time
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from app.core.tool_result import ToolError, ToolResult
from app.services.logging_service import LoggingService
from app.storage.db import get_connection, init_db
from app.tools import knowledge_tool, order_tool, ticket_tool


class ToolGateway:
    """业务工具的唯一受控入口。

    ToolGateway 只负责“能不能调用这个工具、实际路由到哪个 Mock Tool、如何记录
    工具调用日志”。它不做权限判断、风险裁决、重试或降级；这些分别属于
    PolicyService 和后续 FailureHandler。这样可以保持职责边界清晰，避免工具层
    悄悄绕过策略层。
    """

    ALLOWED_TOOLS = {
        "knowledge_tool.query_policy",
        "order_tool.query_order",
        "order_tool.change_address",
        "ticket_tool.create_ticket",
    }

    def __init__(
        self,
        db_path: str | Path | None = None,
        mock_dir: str | Path | None = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path else None
        self.mock_dir = Path(mock_dir) if mock_dir else None
        init_db(self.db_path)

    def call_tool(
        self,
        run_id: str,
        session_id: str,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
        attempt_no: int = 1,
    ) -> ToolResult:
        """执行一次工具调用并写入 tool_call_logs。

        本方法每次只调用工具一次，不做任何重试。后续 FailureHandler 如果判断
        可以重试，会再次调用 ToolGateway，并传入递增后的 attempt_no。
        """
        args = tool_args or {}
        started_at = time.perf_counter()
        result = self._reject_unknown_tool(tool_name)
        if tool_name in self.ALLOWED_TOOLS:
            try:
                result = self._route_tool(tool_name, args)
            except Exception:
                # 这里不记录异常栈，避免内部细节进入日志；后续 FailureHandler
                # 会根据 error_type 判断是否重试或降级。
                result = ToolResult(
                    success=False,
                    tool_name=tool_name,
                    data={},
                    summary="工具调用失败。",
                    error_type="TOOL_EXCEPTION",
                    safe_for_llm=True,
                    error=ToolError(
                        failure_type="TOOL_EXCEPTION",
                        message="工具执行过程中发生异常",
                        retryable=True,
                    ),
                )

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        self._write_tool_call_log(
            run_id=run_id,
            session_id=session_id,
            tool_name=tool_name,
            tool_args=args,
            result=result,
            attempt_no=attempt_no,
            latency_ms=latency_ms,
        )
        return result

    def _route_tool(self, tool_name: str, tool_args: dict[str, Any]) -> ToolResult:
        routes: dict[str, Callable[[dict[str, Any]], ToolResult]] = {
            "knowledge_tool.query_policy": self._call_query_policy,
            "order_tool.query_order": self._call_query_order,
            "order_tool.change_address": self._call_change_address,
            "ticket_tool.create_ticket": self._call_create_ticket,
        }
        return routes[tool_name](tool_args)

    @staticmethod
    def _reject_unknown_tool(tool_name: str) -> ToolResult:
        return ToolResult(
            success=False,
            tool_name=tool_name,
            data={},
            summary="工具不在白名单中，已拒绝执行。",
            error_type="TOOL_NOT_ALLOWED",
            safe_for_llm=True,
            error=ToolError(
                failure_type="TOOL_NOT_ALLOWED",
                message="工具不在 ToolGateway 白名单中",
                retryable=False,
            ),
        )

    @staticmethod
    def _call_query_policy(tool_args: dict[str, Any]) -> ToolResult:
        return knowledge_tool.query_policy(query=str(tool_args.get("query", "")))

    def _call_query_order(self, tool_args: dict[str, Any]) -> ToolResult:
        return order_tool.query_order(
            order_id=str(tool_args.get("order_id", "")),
            mock_dir=self.mock_dir,
            db_path=self.db_path,
        )

    def _call_change_address(self, tool_args: dict[str, Any]) -> ToolResult:
        return order_tool.change_address(
            order_id=str(tool_args.get("order_id", "")),
            new_address=tool_args.get("new_address"),
            mock_dir=self.mock_dir,
            db_path=self.db_path,
        )

    def _call_create_ticket(self, tool_args: dict[str, Any]) -> ToolResult:
        # TODO(Phase 4): /api/chat 或 Workflow 接入时，不能只传
        # ActionPlan.tool_args。主链路必须合并系统上下文：
        # user_id/customer_user_id、action、target_type、target_id、risk_level、
        # source_run_id，确保工单幂等和审计链路都有稳定输入。
        return ticket_tool.create_ticket(
            user_id=str(tool_args.get("user_id", "")),
            action=str(tool_args.get("action", "")),
            target_type=str(tool_args.get("target_type", "")),
            target_id=tool_args.get("target_id"),
            ticket_type=str(tool_args.get("ticket_type", "general")),
            risk_level=str(tool_args.get("risk_level", "L4")),
            description=tool_args.get("description"),
            db_path=self.db_path,
            source_run_id=tool_args.get("source_run_id"),
            parent_run_id=tool_args.get("parent_run_id"),
            pending_action_id=tool_args.get("pending_action_id"),
        )

    def _write_tool_call_log(
        self,
        run_id: str,
        session_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        result: ToolResult,
        attempt_no: int,
        latency_ms: int,
    ) -> None:
        """写入脱敏后的工具调用日志。

        日志只记录参数摘要和结果摘要，不记录完整 ToolResult.data，避免把未来工具
        可能返回的业务详情直接落库。
        """
        sanitized_args = LoggingService.sanitize_payload(tool_args)
        sanitized_result_summary = LoggingService.sanitize_payload(
            {
                "success": result.success,
                "tool_name": result.tool_name,
                "summary": result.summary,
                "error_type": result.error_type,
                "safe_for_llm": result.safe_for_llm,
            }
        )
        status = "SUCCESS" if result.success else "FAILED"
        with get_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO tool_call_logs (
                    id, run_id, session_id, tool_name, attempt_no,
                    tool_args_json, tool_result_summary_json,
                    status, failure_type, latency_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._generate_log_id(),
                    run_id,
                    session_id,
                    tool_name,
                    attempt_no,
                    json.dumps(sanitized_args, ensure_ascii=False, default=str),
                    json.dumps(
                        sanitized_result_summary,
                        ensure_ascii=False,
                        default=str,
                    ),
                    status,
                    result.error_type,
                    latency_ms,
                ),
            )
            connection.commit()

    @staticmethod
    def _generate_log_id() -> str:
        return f"tcl_{uuid4().hex[:16]}"
