import json
from typing import Any

from app.llm.provider import LLMRequest, LLMResponse


DEFAULT_RESPONSE_MAP = {
    "intent": json.dumps(
        {"intent": "order_query", "confidence": 0.9},
        ensure_ascii=False,
    ),
    "planner": json.dumps(
        {
            "action": "query_order",
            "target_type": "order",
            "target_id": "O10086",
            "tool_name": "order_tool.query_order",
        },
        ensure_ascii=False,
    ),
    "response": "请求已处理完成。",
}


class MockLLMProvider:
    """本地 Mock LLM Provider。

    该 provider 只根据 task_type 返回固定文本，不访问外部网络，不读取
    API key。它用于后续 LLM Intent / Planner / ResponseGenerator 的
    接口联调和边界测试。
    """

    name = "mock"

    def __init__(
        self,
        response_map: dict[str, str] | None = None,
        default_text: str = "mock response",
        model_name: str | None = "mock-model",
    ) -> None:
        self.response_map = response_map or DEFAULT_RESPONSE_MAP.copy()
        self.default_text = default_text
        self.model_name = model_name

    def complete(self, request: LLMRequest) -> LLMResponse:
        text = self.response_map.get(request.task_type, self.default_text)
        return LLMResponse(
            text=text,
            provider_name=self.name,
            model_name=self.model_name,
            usage={},
            raw_response=self._safe_raw_response(request),
        )

    def _safe_raw_response(self, request: LLMRequest) -> dict[str, Any]:
        return {
            "provider": "mock",
            "task_type": request.task_type,
            "matched": request.task_type in self.response_map,
        }
