import json
from dataclasses import dataclass, field
from typing import Any

from app.llm.provider import BaseLLMProvider, LLMRequest
from app.services.llm_output_guard import LLMOutputGuard
from app.services.intent_service import RuleBasedIntentClassifier


@dataclass
class LLMIntentClassifier:
    """LLM 意图识别适配器。

    当前只把 provider 返回的 JSON 文本转换为候选 intent。任何解析异常、
    字段缺失或 provider 异常都会回退到规则分类器，避免 LLM 影响主链路稳定性。
    """

    provider: BaseLLMProvider
    fallback_classifier: RuleBasedIntentClassifier = field(
        default_factory=RuleBasedIntentClassifier
    )
    output_guard: LLMOutputGuard | None = None

    def classify(self, message: str) -> str:
        try:
            response = self.provider.complete(
                LLMRequest(
                    system_prompt=(
                        "你是 SafeAgent-CS 的意图识别器，只能输出 JSON。"
                        "格式必须为 {\"schema_version\":\"1.0\","
                        "\"intent\":\"order_query\",\"confidence\":0.9,"
                        "\"entities\":{\"order_id\":\"O10086\"}}。"
                    ),
                    user_prompt=message,
                    task_type="intent",
                    temperature=0.0,
                    metadata={"adapter": "LLMIntentClassifier"},
                )
            )
            payload = self._safe_payload(response.text)
            intent = payload.get("intent")
            if not isinstance(intent, str) or not intent.strip():
                return self._fallback(message)
            return intent
        except Exception:
            return self._fallback(message)

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, Any]:
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("LLM intent output must be a JSON object")
        return payload

    def _safe_payload(self, text: str) -> dict[str, Any]:
        if self.output_guard is None:
            return self._parse_json_object(text)
        result = self.output_guard.guard_intent_output(text)
        if result.fallback_required or result.sanitized_payload is None:
            raise ValueError(result.blocked_reason or "LLM intent guard failed")
        return result.sanitized_payload

    def _fallback(self, message: str) -> str:
        return self.fallback_classifier.classify(message)
