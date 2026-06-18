from typing import Any

from app.core.tool_result import ToolError, ToolResult
from app.tools.adapter import ToolCapability, ToolRequest


class _HttpAdapterStub:
    """真实业务系统 Adapter 的占位实现。

    默认不启用、不发真实网络请求、不读取 API key。后续接真实平台时，应通过
    明确配置和受控 HTTP client 注入完成，不允许在这里偷偷读取环境密钥。
    """

    name: str
    capability: ToolCapability

    def __init__(
        self,
        *,
        base_url: str | None = None,
        enabled: bool = False,
        client: Any | None = None,
    ) -> None:
        self.base_url = base_url
        self.enabled = enabled
        self.client = client

    def execute(self, request: ToolRequest) -> ToolResult:
        if not self.enabled:
            return self._failure("REAL_ADAPTER_DISABLED", "真实业务适配器未启用。")
        if not self.base_url:
            return self._failure("REAL_ADAPTER_NOT_CONFIGURED", "真实业务适配器未配置。")
        if self.client is None:
            return self._failure("REAL_ADAPTER_CLIENT_MISSING", "真实业务客户端未注入。")

        payload = {
            "tool_name": request.tool_name,
            "tool_args": request.tool_args,
            "run_id": request.context.run_id,
            "tool_call_id": request.context.tool_call_id,
            "idempotency_key": request.context.idempotency_key,
        }
        response = self.client.send(
            base_url=self.base_url,
            tool_name=request.tool_name,
            payload=payload,
        )
        return ToolResult(
            success=True,
            tool_name=request.tool_name,
            data={
                "adapter": self.name,
                "request_sent": True,
                "response_summary": str(response),
            },
            summary="真实业务适配器请求已由 fake client 接收。",
            safe_for_llm=True,
        )

    def _failure(self, error_type: str, summary: str) -> ToolResult:
        return ToolResult(
            success=False,
            tool_name=self.name,
            data={},
            summary=summary,
            error_type=error_type,
            safe_for_llm=True,
            error=ToolError(
                failure_type=error_type,
                message=summary,
                retryable=False,
            ),
        )


class HttpOrderAdapterStub(_HttpAdapterStub):
    name = "external_order_tool"
    capability = ToolCapability(
        tool_name=name,
        read_only=False,
        side_effect=True,
        requires_idempotency=True,
        safe_for_llm=True,
    )


class HttpTicketAdapterStub(_HttpAdapterStub):
    name = "external_ticket_tool"
    capability = ToolCapability(
        tool_name=name,
        read_only=False,
        side_effect=True,
        requires_idempotency=True,
        safe_for_llm=True,
    )
