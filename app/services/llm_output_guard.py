import json
from typing import Any

from app.core.llm_models import GuardStatus, LLMGuardResult, SCHEMA_VERSION


class LLMOutputGuard:
    """LLM 原始输出层的基础防线。

    这里处理的是模型返回的原始 JSON 字符串，只做结构和明显风险初筛。
    它不替代 ActionPlanValidator，不判断权限，不访问订单归属，也不调用工具。
    """

    ALLOWED_INTENTS = {
        "policy_query",
        "order_query",
        "address_change",
        "refund_request",
        "complaint",
        "prompt_injection",
        "unknown",
    }
    ALLOWED_ACTIONS = {
        "query_policy",
        "query_order",
        "change_address",
        "request_refund",
        "create_complaint_ticket",
        "security_risk",
        "unknown_action",
    }
    ALLOWED_TARGET_TYPES = {
        "order",
        "policy",
        "ticket",
        "security",
        "unknown",
    }
    # TODO: 后续应抽取共享 ActionCatalog / ToolCatalog，
    # 避免与 ActionPlanValidator 重复维护白名单。
    ALLOWED_TOOLS = {
        "knowledge_tool.query_policy",
        "order_tool.query_order",
        "order_tool.change_address",
        "ticket_tool.create_ticket",
    }
    NO_TOOL_ACTIONS = {"security_risk", "unknown_action"}
    DANGEROUS_KEYWORDS = (
        "export_all_users",
        "dump_database",
        "read_system_prompt",
        "admin_tool",
        "delete_all",
        "api_key",
        "token",
        "system prompt",
    )

    def __init__(self, min_confidence: float = 0.75) -> None:
        self.min_confidence = min_confidence

    def guard_intent_output(self, raw_output: str) -> LLMGuardResult:
        """校验 LLMIntentResult 原始 JSON 输出。"""
        payload_result = self._parse_payload(raw_output)
        if payload_result.guard_status != GuardStatus.VALID.value:
            return payload_result

        payload = payload_result.sanitized_payload or {}
        required_result = self._require_fields(
            payload,
            required_fields=("schema_version", "intent", "confidence", "entities"),
        )
        if required_result:
            return required_result

        schema_result = self._validate_schema_version(payload)
        if schema_result:
            return schema_result

        confidence_result = self._validate_confidence(payload)
        if confidence_result:
            return confidence_result

        if payload["intent"] not in self.ALLOWED_INTENTS:
            return self._invalid_schema("intent 不在允许集合中", payload)
        if not isinstance(payload["entities"], dict):
            return self._invalid_schema("entities 必须是对象", payload)

        return self._valid(payload, confidence=float(payload["confidence"]))

    def guard_action_plan_output(self, raw_output: str) -> LLMGuardResult:
        """校验 LLMActionPlanCandidate 原始 JSON 输出。"""
        payload_result = self._parse_payload(raw_output)
        if payload_result.guard_status != GuardStatus.VALID.value:
            return payload_result

        payload = payload_result.sanitized_payload or {}
        required_result = self._require_fields(
            payload,
            required_fields=(
                "schema_version",
                "intent",
                "action",
                "target_type",
                "target_id",
                "tool_name",
                "tool_args",
                "reason",
                "confidence",
            ),
        )
        if required_result:
            return required_result

        schema_result = self._validate_schema_version(payload)
        if schema_result:
            return schema_result

        confidence_result = self._validate_confidence(payload)
        if confidence_result:
            return confidence_result

        enum_result = self._validate_action_plan_enums(payload)
        if enum_result:
            return enum_result

        tool_result = self._validate_tool_name(payload)
        if tool_result:
            return tool_result

        if not isinstance(payload["tool_args"], dict):
            return self._invalid_schema("tool_args 必须是对象", payload)

        return self._valid(payload, confidence=float(payload["confidence"]))

    def _parse_payload(self, raw_output: str) -> LLMGuardResult:
        if self._contains_dangerous_keyword(raw_output):
            return self._forbidden_output("LLM 输出包含明显危险关键词")

        try:
            payload = json.loads(raw_output)
        except json.JSONDecodeError:
            return LLMGuardResult(
                guard_status=GuardStatus.INVALID_JSON.value,
                sanitized_payload=None,
                fallback_required=True,
                blocked_reason="LLM 输出不是合法 JSON",
                confidence=None,
            )

        if not isinstance(payload, dict):
            return self._invalid_schema("LLM 输出必须是 JSON 对象")
        return self._valid(payload, confidence=None)

    def _require_fields(
        self,
        payload: dict[str, Any],
        required_fields: tuple[str, ...],
    ) -> LLMGuardResult | None:
        for field_name in required_fields:
            if field_name not in payload:
                return self._invalid_schema(f"缺少必要字段: {field_name}", payload)
        return None

    @staticmethod
    def _validate_schema_version(payload: dict[str, Any]) -> LLMGuardResult | None:
        if payload.get("schema_version") != SCHEMA_VERSION:
            return LLMGuardResult(
                guard_status=GuardStatus.SCHEMA_INVALID.value,
                sanitized_payload=payload,
                fallback_required=True,
                blocked_reason="schema_version 缺失或不受支持",
                confidence=None,
            )
        return None

    def _validate_confidence(
        self,
        payload: dict[str, Any],
    ) -> LLMGuardResult | None:
        confidence = payload.get("confidence")
        if not isinstance(confidence, int | float):
            return self._invalid_schema("confidence 必须是数字", payload)
        if confidence < self.min_confidence:
            return LLMGuardResult(
                guard_status=GuardStatus.LOW_CONFIDENCE.value,
                sanitized_payload=payload,
                fallback_required=True,
                blocked_reason="confidence 低于阈值",
                confidence=float(confidence),
            )
        return None

    def _validate_action_plan_enums(
        self,
        payload: dict[str, Any],
    ) -> LLMGuardResult | None:
        if payload["intent"] not in self.ALLOWED_INTENTS:
            return self._invalid_schema("intent 不在允许集合中", payload)
        if payload["action"] not in self.ALLOWED_ACTIONS:
            return self._invalid_schema("action 不在允许集合中", payload)
        if payload["target_type"] not in self.ALLOWED_TARGET_TYPES:
            return self._invalid_schema("target_type 不在允许集合中", payload)
        return None

    def _validate_tool_name(
        self,
        payload: dict[str, Any],
    ) -> LLMGuardResult | None:
        action = payload["action"]
        tool_name = payload["tool_name"]

        if tool_name is None:
            if action in self.NO_TOOL_ACTIONS:
                return None
            return self._invalid_schema("该 action 必须携带 tool_name", payload)

        if tool_name not in self.ALLOWED_TOOLS:
            return self._forbidden_output("tool_name 不在候选工具集合中", payload)
        return None

    def _contains_dangerous_keyword(self, raw_output: str) -> bool:
        raw_text = raw_output.lower()
        return any(keyword in raw_text for keyword in self.DANGEROUS_KEYWORDS)

    @staticmethod
    def _valid(
        payload: dict[str, Any],
        confidence: float | None,
    ) -> LLMGuardResult:
        return LLMGuardResult(
            guard_status=GuardStatus.VALID.value,
            sanitized_payload=payload,
            fallback_required=False,
            blocked_reason=None,
            confidence=confidence,
        )

    @staticmethod
    def _invalid_schema(
        reason: str,
        payload: dict[str, Any] | None = None,
    ) -> LLMGuardResult:
        return LLMGuardResult(
            guard_status=GuardStatus.SCHEMA_INVALID.value,
            sanitized_payload=payload,
            fallback_required=True,
            blocked_reason=reason,
            confidence=None,
        )

    @staticmethod
    def _forbidden_output(
        reason: str,
        payload: dict[str, Any] | None = None,
    ) -> LLMGuardResult:
        return LLMGuardResult(
            guard_status=GuardStatus.FORBIDDEN_OUTPUT.value,
            sanitized_payload=payload,
            fallback_required=True,
            blocked_reason=reason,
            confidence=None,
        )
