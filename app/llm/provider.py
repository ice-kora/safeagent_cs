from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMProviderError(Exception):
    """LLM Provider 层基础异常。"""


class LLMProviderNotFoundError(LLMProviderError):
    """请求的 LLM Provider 未注册时抛出。"""


SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "bearer_token",
}


@dataclass(frozen=True)
class LLMRequest:
    """统一 LLM 请求契约。

    该对象只承载模型调用所需的提示词和任务类型，不保存 API key。
    真实 provider 后续应从受控配置层读取凭据，不能把凭据塞进 request。
    """

    system_prompt: str
    user_prompt: str
    task_type: str
    temperature: float = 0.0
    max_tokens: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _raise_if_secret_keys(self.metadata, "metadata")


@dataclass(frozen=True)
class LLMResponse:
    """统一 LLM 响应契约。

    text 是主输出。usage 和 raw_response 允许为空，但不能携带密钥、
    token 或其他敏感凭据字段。
    """

    text: str
    provider_name: str
    model_name: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    raw_response: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        _raise_if_secret_keys(self.usage, "usage")
        if self.raw_response is not None:
            _raise_if_secret_keys(self.raw_response, "raw_response")


class BaseLLMProvider(Protocol):
    """LLM Provider 协议。

    该协议只定义文本补全接口，不包含工具调用能力。
    """

    name: str

    def complete(self, request: LLMRequest) -> LLMResponse:
        ...


def _raise_if_secret_keys(payload: dict[str, Any], field_name: str) -> None:
    for key, value in payload.items():
        normalized_key = str(key).lower().replace("-", "_")
        if normalized_key in SECRET_KEYS:
            raise LLMProviderError(f"{field_name} must not contain secret key: {key}")
        if isinstance(value, dict):
            _raise_if_secret_keys(value, field_name)
