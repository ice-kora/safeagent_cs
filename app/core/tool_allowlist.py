"""显式工具白名单。

v0.6-Tool-R1 起白名单与 ToolAdapterRegistry 注册解耦：

- ``ToolAdapterRegistry.names()`` 只表示“已注册可执行的 adapter 目录”，
  它不再等价于“对 LLM / 主链路暴露的安全工具清单”。
- 本模块的 ``ALLOWED_TOOL_NAMES`` 是手写常量，是 ToolGateway 在执行工具前
  必须通过的第二道闸门。即使某个 adapter 被 register 进 registry，只要
  其 ``tool_name`` 不在本白名单中，ToolGateway 也会直接拒绝执行。

新增对外部业务系统 adapter 的接入必须同时满足两步：
1. 通过 build_adapter_registry 注册进 registry；
2. 显式把对应 ``tool_name`` 加入本白名单。
任何一步缺失都应 fail closed。
"""

import os

ALLOWED_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "knowledge_tool.query_policy",
        "order_tool.query_order",
        "order_tool.change_address",
        "ticket_tool.create_ticket",
    }
)

OPTIONAL_MCP_TOOL_NAMES: frozenset[str] = frozenset({"mcp.mock.echo"})


def is_tool_allowed(tool_name: str) -> bool:
    """判断工具名是否在显式安全白名单中。

    与 registry 是否注册无关；这是 ToolGateway 执行前的独立安全校验，
    避免“adapter 注册即暴露”。
    """
    if tool_name in ALLOWED_TOOL_NAMES:
        return True
    return (
        os.getenv("SAFEAGENT_MCP_MOCK_ENABLED", "").strip().lower()
        in {"1", "true", "yes", "on"}
        and tool_name in OPTIONAL_MCP_TOOL_NAMES
    )
