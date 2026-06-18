import json
from dataclasses import dataclass, field
from typing import Any

from app.core.action_plan import ActionPlan
from app.llm.provider import BaseLLMProvider, LLMRequest
from app.services.llm_output_guard import LLMOutputGuard
from app.services.planner_service import RuleBasedActionPlanner


@dataclass
class LLMActionPlanner:
    """LLM ActionPlan 生成适配器。

    该类只把 provider 返回的 JSON 文本转换为候选 ActionPlan，不执行工具，
    不做权限判断，也不替代 ActionPlanValidator。
    """

    provider: BaseLLMProvider
    fallback_planner: RuleBasedActionPlanner = field(
        default_factory=RuleBasedActionPlanner
    )
    output_guard: LLMOutputGuard | None = None

    def plan(self, *, intent: str, message: str) -> ActionPlan:
        try:
            response = self.provider.complete(
                LLMRequest(
                    system_prompt=(
                        "你是 SafeAgent-CS 的 ActionPlan 生成器，只能输出 JSON。"
                        "输出只是候选计划，不能调用工具。格式必须包含 "
                        "schema_version、intent、action、target_type、target_id、"
                        "tool_name、tool_args、reason、confidence。"
                    ),
                    user_prompt=message,
                    task_type="planner",
                    temperature=0.0,
                    metadata={
                        "adapter": "LLMActionPlanner",
                        "intent": intent,
                    },
                )
            )
            payload = self._safe_payload(response.text)
            return self._build_action_plan(payload)
        except Exception:
            return self._fallback(intent, message)

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, Any]:
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("LLM planner output must be a JSON object")
        return payload

    def _safe_payload(self, text: str) -> dict[str, Any]:
        if self.output_guard is None:
            return self._parse_json_object(text)
        result = self.output_guard.guard_action_plan_output(text)
        if result.fallback_required or result.sanitized_payload is None:
            raise ValueError(result.blocked_reason or "LLM planner guard failed")
        return result.sanitized_payload

    @staticmethod
    def _build_action_plan(payload: dict[str, Any]) -> ActionPlan:
        required_string_fields = ("intent", "action", "target_type")
        for field_name in required_string_fields:
            value = payload.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"LLM planner field is invalid: {field_name}")

        for optional_string_field in ("target_id", "tool_name", "reason"):
            value = payload.get(optional_string_field)
            if value is not None and not isinstance(value, str):
                raise ValueError(
                    f"LLM planner field is invalid: {optional_string_field}"
                )

        tool_args = payload.get("tool_args", {})
        if not isinstance(tool_args, dict):
            raise ValueError("LLM planner tool_args must be a JSON object")

        return ActionPlan(
            intent=payload["intent"],
            action=payload["action"],
            target_type=payload["target_type"],
            target_id=payload.get("target_id"),
            tool_name=payload.get("tool_name"),
            tool_args=tool_args,
            reason=payload.get("reason") or "LLM 生成候选 ActionPlan。",
        )

    def _fallback(self, intent: str, message: str) -> ActionPlan:
        return self.fallback_planner.plan(intent=intent, message=message)
