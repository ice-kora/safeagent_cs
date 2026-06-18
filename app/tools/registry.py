from pathlib import Path
from typing import Any, Callable

from app.core.config import (
    TOOL_BACKEND_EXTERNAL_STUB,
    TOOL_BACKEND_MOCK,
    VALID_TOOL_BACKENDS,
)
from app.core.tool_result import ToolResult
from app.tools.adapter import ToolAdapter, ToolExecutionContext, ToolRequest
from app.tools.mock_adapters import (
    KnowledgeToolAdapter,
    OrderChangeAddressAdapter,
    OrderQueryAdapter,
    TicketCreateAdapter,
)
from app.tools.real_adapters import HttpOrderAdapterStub, HttpTicketAdapterStub


ToolHandler = Callable[[dict[str, Any]], ToolResult]


class ToolAdapterNotFoundError(KeyError):
    """工具适配器不存在时抛出的明确异常。"""


class ToolAdapterRegistry:
    """ToolAdapter 注册表。

    这是代码级 adapter 目录，不是 MCP，也不做动态插件加载。它只负责
    tool_name -> adapter 的稳定映射，不负责权限、风险、重试或日志。
    """

    def __init__(self, adapters: list[ToolAdapter] | None = None) -> None:
        self._adapters: dict[str, ToolAdapter] = {}
        for adapter in adapters if adapters is not None else _default_mock_adapters():
            self.register(adapter)

    def register(self, adapter: ToolAdapter) -> None:
        """注册 adapter；同名注册采用覆盖策略，便于测试替换。"""
        self._adapters[adapter.name] = adapter

    def get(self, tool_name: str) -> ToolAdapter:
        try:
            return self._adapters[tool_name]
        except KeyError as exc:
            raise ToolAdapterNotFoundError(f"Tool adapter not found: {tool_name}") from exc

    def names(self) -> list[str]:
        return sorted(self._adapters)

    def capabilities(self):
        return {name: self._adapters[name].capability for name in self.names()}

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._adapters

    def list_tools(self) -> list[str]:
        return self.names()


class ToolRegistry:
    """旧 ToolRegistry 兼容外壳。

    新主链路应使用 ToolAdapterRegistry。保留本类是为了不打断已有测试和
    少量内部调用，它通过 adapter.execute 转接，不重新实现工具逻辑。
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        mock_dir: str | Path | None = None,
        adapter_registry: ToolAdapterRegistry | None = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path else None
        self.mock_dir = Path(mock_dir) if mock_dir else None
        self.adapter_registry = adapter_registry or ToolAdapterRegistry()

    def has_tool(self, tool_name: str) -> bool:
        return self.adapter_registry.has_tool(tool_name)

    def get_handler(self, tool_name: str) -> ToolHandler:
        adapter = self.adapter_registry.get(tool_name)

        def handler(tool_args: dict[str, Any]) -> ToolResult:
            context = ToolExecutionContext(
                run_id=None,
                session_id=None,
                user_id=str(tool_args.get("user_id", "unknown_user")),
                tenant_id=tool_args.get("tenant_id"),
                action_plan=None,
                tool_call_id=None,
                idempotency_key=tool_args.get("idempotency_key"),
                action_fingerprint=None,
                metadata={
                    "db_path": str(self.db_path) if self.db_path else None,
                    "mock_dir": str(self.mock_dir) if self.mock_dir else None,
                },
            )
            return adapter.execute(
                ToolRequest(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    context=context,
                )
            )

        return handler

    def list_tools(self) -> list[str]:
        return self.adapter_registry.names()


def _default_mock_adapters() -> list[ToolAdapter]:
    return [
        KnowledgeToolAdapter(),
        OrderQueryAdapter(),
        OrderChangeAddressAdapter(),
        TicketCreateAdapter(),
    ]


def build_adapter_registry(
    backend: str = TOOL_BACKEND_MOCK,
    *,
    stub_base_url: str | None = None,
    stub_client: Any | None = None,
) -> ToolAdapterRegistry:
    """按 tool_backend 配置构造 ToolAdapterRegistry。

    v0.6-Tool-R1 配置化接入入口。ToolGateway 在未显式注入 registry 时调用本工厂，
    根据 ``SAFEAGENT_TOOL_BACKEND`` 选择 adapter 集合。

    - ``mock``：默认 4 个本地 Mock Adapter，不发任何网络请求。
    - ``external_stub``：注册 HTTP adapter stub。但**默认 disabled**（fail-closed），
      只有显式传入 ``stub_client`` 和 ``stub_base_url`` 时才 enabled。
      不读取真实业务 API key、不发真实网络请求。

    注意：external_stub 注册的 adapter 名（``external_order_tool`` /
    ``external_ticket_tool``）不在 ``ALLOWED_TOOL_NAMES`` 中，因此即使配置开了
    external_stub，ToolGateway 默认白名单仍会拒绝它们。要真正对外暴露需后续
    同时把名字加入白名单（两步 fail-closed 设计）。

    本函数不直接读环境变量，所有外部输入由调用方显式传入，保持可测性。
    非法 backend 回退 mock，避免误接实验性路径。
    """
    if backend not in VALID_TOOL_BACKENDS:
        backend = TOOL_BACKEND_MOCK

    if backend == TOOL_BACKEND_MOCK:
        return ToolAdapterRegistry()

    if backend == TOOL_BACKEND_EXTERNAL_STUB:
        enabled = bool(stub_client is not None and stub_base_url)
        stub_kwargs = {
            "enabled": enabled,
            "base_url": stub_base_url,
            "client": stub_client,
        }
        adapters: list[ToolAdapter] = [
            *_default_mock_adapters(),
            HttpOrderAdapterStub(**stub_kwargs),
            HttpTicketAdapterStub(**stub_kwargs),
        ]
        return ToolAdapterRegistry(adapters)

    # 理论不可达：非法 backend 已被回退为 mock。
    return ToolAdapterRegistry()
