import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from app.llm.provider import LLMProviderError, LLMRequest, LLMResponse


HttpPost = Callable[
    [str, dict[str, str], dict[str, Any], float],
    dict[str, Any],
]


@dataclass
class OpenAICompatibleLLMProvider:
    """OpenAI 兼容 Chat Completions Provider。

    该 provider 只从环境变量或显式参数接收配置，不保存到日志，不把
    api_key 放入 raw_response。它实现真实 LLM smoke path，但不具备工具调用能力。
    """

    base_url: str
    api_key: str
    model: str
    name: str = "openai_compatible"
    timeout_seconds: float = 30.0
    http_post: HttpPost | None = None

    def __post_init__(self) -> None:
        if not self.base_url:
            raise LLMProviderError("LLM base_url is required")
        if not self.api_key:
            raise LLMProviderError("LLM api_key is required")
        if not self.model:
            raise LLMProviderError("LLM model is required")
        if self.timeout_seconds <= 0:
            raise LLMProviderError("LLM timeout_seconds must be positive")

    @classmethod
    def from_env(cls) -> "OpenAICompatibleLLMProvider":
        """从环境变量创建 provider。

        优先读取 SAFEAGENT_LLM_*，其次兼容 DEEPSEEK_*。
        """
        api_key = os.getenv("SAFEAGENT_LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        base_url = os.getenv("SAFEAGENT_LLM_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL")
        model = os.getenv("SAFEAGENT_LLM_MODEL") or os.getenv("DEEPSEEK_MODEL")
        provider_name = os.getenv("SAFEAGENT_LLM_PROVIDER") or "openai_compatible"
        timeout = float(os.getenv("SAFEAGENT_LLM_TIMEOUT_SECONDS", "30"))

        if not api_key:
            raise LLMProviderError("LLM API key is missing")
        if not base_url:
            raise LLMProviderError("LLM base URL is missing")
        if not model:
            raise LLMProviderError("LLM model is missing")

        return cls(
            name=provider_name,
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout,
        )

    def complete(self, request: LLMRequest) -> LLMResponse:
        endpoint = _chat_completions_endpoint(self.base_url)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        try:
            response_payload = (
                self.http_post or _urllib_post_json
            )(endpoint, headers, payload, self.timeout_seconds)
        except Exception as exc:
            raise LLMProviderError("LLM provider request failed") from exc

        try:
            text = response_payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError("LLM provider response missing content") from exc

        if not isinstance(text, str):
            raise LLMProviderError("LLM provider response content must be text")

        usage = response_payload.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}

        return LLMResponse(
            text=text,
            provider_name=self.name,
            model_name=self.model,
            usage=usage,
            raw_response={
                "provider": self.name,
                "model": self.model,
                "has_choices": bool(response_payload.get("choices")),
            },
        )


def _chat_completions_endpoint(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _urllib_post_json(
    endpoint: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise LLMProviderError("LLM HTTP request failed") from exc

    try:
        parsed = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("LLM HTTP response is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise LLMProviderError("LLM HTTP response must be a JSON object")
    return parsed
