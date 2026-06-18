import json
from typing import Any

from app.core.action_plan import ActionPlan
from app.core.llm_models import (
    LLMActionPlanCandidate,
    LLMIntentResult,
    SCHEMA_VERSION,
)


class LLMContractError(ValueError):
    """LLM 输出不符合结构契约时抛出。"""


def parse_intent_result(raw_output: str) -> LLMIntentResult:
    """将 LLM 原始 JSON 文本解析为 LLMIntentResult。"""
    payload = _parse_json_object(raw_output)
    _validate_schema_version(payload)

    intent = payload.get("intent")
    confidence = payload.get("confidence")
    entities = payload.get("entities", {})
    raw_user_message_hash = payload.get("raw_user_message_hash")

    if not isinstance(intent, str) or not intent.strip():
        raise LLMContractError("intent must be a non-empty string")
    if not isinstance(confidence, int | float):
        raise LLMContractError("confidence must be a number")
    if not isinstance(entities, dict):
        raise LLMContractError("entities must be an object")
    if raw_user_message_hash is not None and not isinstance(
        raw_user_message_hash,
        str,
    ):
        raise LLMContractError("raw_user_message_hash must be a string or null")

    return LLMIntentResult(
        intent=intent,
        confidence=float(confidence),
        entities={str(key): str(value) for key, value in entities.items()},
        raw_user_message_hash=raw_user_message_hash,
        schema_version=payload["schema_version"],
    )


def parse_action_plan_candidate(raw_output: str) -> LLMActionPlanCandidate:
    """将 LLM 原始 JSON 文本解析为候选 ActionPlan 契约。"""
    payload = _parse_json_object(raw_output)
    _validate_schema_version(payload)

    for field_name in ("intent", "action", "reason"):
        _require_string(payload, field_name)
    _require_optional_string(payload, "target_type")
    _require_optional_string(payload, "target_id")
    _require_optional_string(payload, "tool_name")

    confidence = payload.get("confidence")
    if not isinstance(confidence, int | float):
        raise LLMContractError("confidence must be a number")

    tool_args = payload.get("tool_args")
    if not isinstance(tool_args, dict):
        raise LLMContractError("tool_args must be an object")

    return LLMActionPlanCandidate(
        intent=payload["intent"],
        action=payload["action"],
        target_type=payload.get("target_type"),
        target_id=payload.get("target_id"),
        tool_name=payload.get("tool_name"),
        tool_args=tool_args,
        reason=payload["reason"],
        confidence=float(confidence),
        schema_version=payload["schema_version"],
    )


def candidate_to_action_plan(candidate: LLMActionPlanCandidate) -> ActionPlan:
    """将通过契约解析的候选结构转换为内部 ActionPlan。"""
    return ActionPlan(
        intent=candidate.intent,
        action=candidate.action,
        target_type=candidate.target_type,
        target_id=candidate.target_id,
        tool_name=candidate.tool_name,
        tool_args=dict(candidate.tool_args),
        reason=candidate.reason,
    )


def _parse_json_object(raw_output: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise LLMContractError("LLM output must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise LLMContractError("LLM output must be a JSON object")
    return payload


def _validate_schema_version(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise LLMContractError("schema_version must be 1.0")


def _require_string(payload: dict[str, Any], field_name: str) -> None:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise LLMContractError(f"{field_name} must be a non-empty string")


def _require_optional_string(payload: dict[str, Any], field_name: str) -> None:
    value = payload.get(field_name)
    if value is not None and not isinstance(value, str):
        raise LLMContractError(f"{field_name} must be a string or null")
