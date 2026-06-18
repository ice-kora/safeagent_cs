from app.llm.mock_provider import MockLLMProvider
from app.llm.provider import BaseLLMProvider, LLMProviderNotFoundError


class LLMProviderRegistry:
    """LLM Provider 注册表。

    当前只用于 provider 查找和替换，不承担模式路由、权限判断或工具调用。
    重复注册同名 provider 时采用覆盖策略，便于测试和后续环境替换。
    """

    def __init__(self, register_mock: bool = True) -> None:
        self._providers: dict[str, BaseLLMProvider] = {}
        if register_mock:
            self.register(MockLLMProvider())

    def register(self, provider: BaseLLMProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> BaseLLMProvider:
        provider = self._providers.get(name)
        if provider is None:
            raise LLMProviderNotFoundError(f"LLM provider not found: {name}")
        return provider

    def names(self) -> list[str]:
        return sorted(self._providers)
