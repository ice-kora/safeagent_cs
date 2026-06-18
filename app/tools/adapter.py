from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.core.action_plan import ActionPlan
from app.core.tool_result import ToolResult


@dataclass(frozen=True)
class ToolExecutionContext:
    """一次工具调用的最小执行上下文。

    上下文只保存审计和幂等所需字段，不包含 API key、完整手机号、完整地址、
    支付信息等敏感数据。权限裁决已经在 ToolGateway 之前由 PolicyService 完成。
    """

    run_id: str | None
    session_id: str | None
    user_id: str
    tenant_id: str | None
    action_plan: ActionPlan | None
    tool_call_id: str | None
    idempotency_key: str | None
    action_fingerprint: str | None
    attempt_no: int = 1
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ToolRequest:
    """ToolGateway 传递给 ToolAdapter 的统一请求结构。"""

    tool_name: str
    tool_args: dict[str, Any]
    context: ToolExecutionContext


@dataclass(frozen=True)
class ToolCapability:
    """工具能力声明，用于审计和 side-effect 约束。"""

    tool_name: str
    read_only: bool
    side_effect: bool
    requires_idempotency: bool
    safe_for_llm: bool


class ToolAdapter(Protocol):
    """业务工具适配器协议。

    Adapter 只执行具体工具逻辑，不调用 PolicyService，不反向调用 ToolGateway，
    也不决定 ALLOW / DENY 等策略结果。
    """

    name: str
    capability: ToolCapability

    def execute(self, request: ToolRequest) -> ToolResult:
        ...
