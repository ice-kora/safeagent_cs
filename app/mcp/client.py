from typing import Any


class MockMCPClient:
    """本地 MCP client mock，不做网络调用。"""

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "tool_name": tool_name,
            "arguments_echo": arguments,
            "status": "ok",
            "transport": "mock",
        }
