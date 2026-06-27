import json
from dataclasses import dataclass, field
from typing import Any

from app.llm.contract import parse_intent_result
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
    last_debug_info: dict[str, Any] = field(default_factory=dict, init=False)

    def classify(self, message: str) -> str:
        self.last_debug_info = self._base_debug_info()
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
            self.last_debug_info.update(
                {
                    "provider": response.provider_name,
                    "model": response.model_name,
                }
            )
            try:
                candidate = parse_intent_result(response.text)
                self.last_debug_info["contract_status"] = "VALID"
                self.last_debug_info["parse_status"] = "VALID"
                self.last_debug_info["candidate_intent"] = {
                    "schema_version": candidate.schema_version,
                    "intent": candidate.intent,
                    "confidence": candidate.confidence,
                    "entity_keys": sorted(candidate.entities.keys()),
                }
                self._safe_payload(response.text)
                return candidate.intent
            except Exception:
                if self.output_guard is not None:
                    raise
                return self._legacy_intent(response.text)
        except Exception as exc:
            self._record_fallback(exc)
            return self._fallback(message)

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, Any]:
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("LLM intent output must be a JSON object")
        return payload

    def _safe_payload(self, text: str) -> dict[str, Any]:
        if self.output_guard is None:
            self.last_debug_info.update(
                {
                    "guard_enabled": False,
                    "guard_status": "SKIPPED",
                    "fallback_required": False,
                }
            )
            return self._parse_json_object(text)
        result = self.output_guard.guard_intent_output(text)
        self.last_debug_info.update(
            {
                "guard_enabled": True,
                "guard_status": result.guard_status,
                "guard_reason": result.blocked_reason,
                "fallback_required": result.fallback_required,
                "guard_confidence": result.confidence,
            }
        )
        if result.fallback_required or result.sanitized_payload is None:
            raise ValueError(result.blocked_reason or "LLM intent guard failed")
        return result.sanitized_payload

    def _fallback(self, message: str) -> str:
        return self.fallback_classifier.classify(message)

    def _legacy_intent(self, text: str) -> str:
        payload = self._safe_payload(text)
        intent = payload.get("intent")
        if not isinstance(intent, str) or not intent.strip():
            raise ValueError("legacy LLM intent output missing intent")
        self.last_debug_info.update(
            {
                "contract_status": "LEGACY_JSON",
                "parse_status": "LEGACY_JSON",
                "candidate_intent": {
                    "schema_version": None,
                    "intent": intent,
                    "confidence": payload.get("confidence"),
                    "entity_keys": sorted((payload.get("entities") or {}).keys())
                    if isinstance(payload.get("entities"), dict)
                    else [],
                },
            }
        )
        return intent

    def _base_debug_info(self) -> dict[str, Any]:
        return {
            "llm_enabled": True,
            "adapter": "LLMIntentClassifier",
            "task_type": "intent",
            "provider": getattr(self.provider, "name", "unknown"),
            "model": None,
            "guard_enabled": self.output_guard is not None,
            "fallback_used": False,
            "fallback_reason": None,
        }

    def _record_fallback(self, exc: Exception) -> None:
        self.last_debug_info.update(
            {
                "contract_status": self.last_debug_info.get(
                    "contract_status", "FAILED"
                ),
                "parse_status": self.last_debug_info.get("parse_status", "FAILED"),
                "fallback_used": True,
                "fallback_reason": exc.__class__.__name__,
                "fallback_message": str(exc)[:160],
            }
        )
