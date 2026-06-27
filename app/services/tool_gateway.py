import json
import os
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.action_plan import ActionPlan
from app.core.config import get_settings
from app.core.idempotency import build_tool_idempotency_facts
from app.core.tool_allowlist import is_tool_allowed
from app.core.tool_result import ToolError, ToolResult
from app.services.logging_service import LoggingService
from app.storage.runtime_store import get_runtime_store
from app.tools.adapter import ToolExecutionContext, ToolRequest
from app.tools.registry import (
    ToolAdapterNotFoundError,
    ToolAdapterRegistry,
    build_adapter_registry,
)


class ToolGateway:
    """业务工具的唯一受控入口。

    ToolGateway 只负责“能不能调用这个工具、实际路由到哪个 Mock Tool、如何记录
    工具调用日志”。它不做权限判断、风险裁决、重试或降级；这些分别属于
    PolicyService 和后续 FailureHandler。这样可以保持职责边界清晰，避免工具层
    悄悄绕过策略层。

    v0.6-Tool-R1 起 call_tool 增加两道独立闸门：
    1. ``is_tool_allowed`` 显式白名单（与 registry 注册解耦）；
    2. ``adapter_registry.has_tool`` adapter 目录校验。
    两者都通过才会执行 adapter.execute。legacy 的 monkeypatch get_handler 路径
    已移除，测试应通过 ``adapter_registry=`` 注入 fake adapter。
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        mock_dir: str | Path | None = None,
        adapter_registry: ToolAdapterRegistry | None = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path else None
        self.mock_dir = Path(mock_dir) if mock_dir else None
        self.adapter_registry = adapter_registry or build_adapter_registry(
            get_settings().tool_backend
        )
        if (
            os.getenv("SAFEAGENT_MCP_MOCK_ENABLED", "").strip().lower()
            in {"1", "true", "yes", "on"}
            and not self.adapter_registry.has_tool("mcp.mock.echo")
        ):
            from app.tools.mcp_adapter import MCPToolAdapter

            self.adapter_registry.register(MCPToolAdapter())
        self.runtime_store = get_runtime_store(db_path=self.db_path)

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
        facts = build_tool_idempotency_facts(
            tenant_id=_optional_text(args.get("tenant_id")),
            user_id=_optional_text(args.get("customer_user_id") or args.get("user_id"))
            or "unknown_user",
            tool_name=tool_name,
            action_plan=_build_action_context(tool_name, args),
        )
        started_at = time.perf_counter()
        result = self._enforce_allowlist(tool_name)
        if result is None and self.adapter_registry.has_tool(tool_name):
            try:
                adapter = self.adapter_registry.get(tool_name)
                request = ToolRequest(
                    tool_name=tool_name,
                    tool_args=args,
                    context=ToolExecutionContext(
                        run_id=run_id,
                        session_id=session_id,
                        user_id=_optional_text(
                            args.get("customer_user_id") or args.get("user_id")
                        )
                        or "unknown_user",
                        tenant_id=_optional_text(args.get("tenant_id")),
                        action_plan=_build_action_plan(tool_name, args),
                        tool_call_id=facts.tool_call_id,
                        idempotency_key=facts.idempotency_key,
                        action_fingerprint=facts.action_fingerprint,
                        attempt_no=attempt_no,
                        metadata={
                            "db_path": str(self.db_path) if self.db_path else None,
                            "mock_dir": str(self.mock_dir) if self.mock_dir else None,
                        },
                    ),
                )
                result = adapter.execute(request)
            except ToolAdapterNotFoundError:
                result = self._reject_not_registered(tool_name)
            except Exception:
                # 这里不记录异常栈，避免内部细节进入日志；后续 FailureHandler
                # 会根据 error_type 判断是否重试或降级。
                result = self._tool_exception_result(tool_name)
        elif result is None:
            # 白名单通过但 registry 未注册该工具：当作未注册工具拒绝。
            result = self._reject_not_registered(tool_name)

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        self._write_tool_call_log(
            run_id=run_id,
            session_id=session_id,
            tool_name=tool_name,
            tool_args=args,
            result=result,
            attempt_no=attempt_no,
            latency_ms=latency_ms,
            tool_call_id=facts.tool_call_id,
            idempotency_key=facts.idempotency_key,
            action_fingerprint=facts.action_fingerprint,
        )
        return result

    def _enforce_allowlist(self, tool_name: str) -> ToolResult | None:
        """显式白名单闸门。返回拒绝结果或 None（表示通过）。"""
        if is_tool_allowed(tool_name):
            return None
        return ToolResult(
            success=False,
            tool_name=tool_name,
            data={},
            summary="工具未进入显式安全白名单，已拒绝执行。",
            error_type="TOOL_NOT_IN_ALLOWLIST",
            safe_for_llm=True,
            error=ToolError(
                failure_type="TOOL_NOT_IN_ALLOWLIST",
                message="工具未进入显式安全白名单",
                retryable=False,
            ),
        )

    @staticmethod
    def _reject_not_registered(tool_name: str) -> ToolResult:
        return ToolResult(
            success=False,
            tool_name=tool_name,
            data={},
            summary="工具未在 ToolGateway 中注册，已拒绝执行。",
            error_type="TOOL_NOT_REGISTERED",
            safe_for_llm=True,
            error=ToolError(
                failure_type="TOOL_NOT_REGISTERED",
                message="工具未在 ToolGateway 中注册",
                retryable=False,
            ),
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
        tool_call_id: str | None = None,
        idempotency_key: str | None = None,
        action_fingerprint: str | None = None,
    ) -> None:
        """写入脱敏后的工具调用日志。

        日志只记录参数摘要和结果摘要，不记录完整 ToolResult.data，避免把未来工具
        可能返回的业务详情直接落库。
        """
        if not (tool_call_id and idempotency_key and action_fingerprint):
            facts = build_tool_idempotency_facts(
                tenant_id=_optional_text(tool_args.get("tenant_id")),
                user_id=_optional_text(
                    tool_args.get("customer_user_id") or tool_args.get("user_id")
                )
                or "unknown_user",
                tool_name=tool_name,
                action_plan=_build_action_context(tool_name, tool_args),
            )
            tool_call_id = facts.tool_call_id
            idempotency_key = facts.idempotency_key
            action_fingerprint = facts.action_fingerprint
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
        self.runtime_store.insert_tool_call_log(
            {
                "id": self._generate_log_id(),
                "tool_call_id": tool_call_id,
                "idempotency_key": idempotency_key,
                "action_fingerprint": action_fingerprint,
                "run_id": run_id,
                "session_id": session_id,
                "tool_name": tool_name,
                "attempt_no": attempt_no,
                "tool_args_json": json.dumps(
                    sanitized_args,
                    ensure_ascii=False,
                    default=str,
                ),
                "tool_result_summary_json": json.dumps(
                    sanitized_result_summary,
                    ensure_ascii=False,
                    default=str,
                ),
                "status": status,
                "failure_type": result.error_type,
                "latency_ms": latency_ms,
            }
        )

    @staticmethod
    def _generate_log_id() -> str:
        return f"tcl_{uuid4().hex[:16]}"

    @staticmethod
    def _tool_exception_result(tool_name: str) -> ToolResult:
        return ToolResult(
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


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_action_context(tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "action": tool_args.get("action"),
        "target_type": tool_args.get("target_type"),
        "target_id": tool_args.get("target_id") or tool_args.get("order_id"),
        "tool_args": tool_args,
    }


def _build_action_plan(tool_name: str, tool_args: dict[str, Any]) -> ActionPlan | None:
    action = tool_args.get("action")
    if not action:
        return None
    return ActionPlan(
        intent=str(tool_args.get("intent", "")),
        action=str(action),
        target_type=tool_args.get("target_type"),
        target_id=tool_args.get("target_id") or tool_args.get("order_id"),
        tool_name=tool_name,
        tool_args=tool_args,
        reason=str(tool_args.get("reason", "")),
    )
