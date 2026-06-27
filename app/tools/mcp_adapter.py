from dataclasses import dataclass, field

from app.core.tool_result import ToolError, ToolResult
from app.mcp.client import MockMCPClient
from app.services.logging_service import LoggingService
from app.tools.adapter import ToolCapability, ToolRequest


@dataclass
class MCPToolAdapter:
    """MCP ToolAdapter skeleton。

    Adapter 只把 ToolGateway 的请求转给 MCP client，不做 Policy 决策，也不
    反向调用 ToolGateway。
    """

    name: str = "mcp.mock.echo"
    client: MockMCPClient = field(default_factory=MockMCPClient)
    capability: ToolCapability = field(
        default_factory=lambda: ToolCapability(
            tool_name="mcp.mock.echo",
            read_only=True,
            side_effect=False,
            requires_idempotency=False,
            safe_for_llm=True,
        )
    )

    def execute(self, request: ToolRequest) -> ToolResult:
        try:
            payload = self.client.call_tool(
                tool_name=request.tool_name,
                arguments=LoggingService.sanitize_payload(request.tool_args),
            )
        except Exception:
            return ToolResult(
                success=False,
                tool_name=request.tool_name,
                data={},
                summary="MCP mock 工具调用失败。",
                error_type="MCP_TOOL_FAILED",
                safe_for_llm=True,
                error=ToolError(
                    failure_type="MCP_TOOL_FAILED",
                    message="MCP mock 工具调用失败",
                    retryable=False,
                ),
            )
        return ToolResult(
            success=True,
            tool_name=request.tool_name,
            data=LoggingService.sanitize_payload(payload),
            summary="MCP mock 工具已通过 ToolGateway 执行。",
            safe_for_llm=True,
        )
