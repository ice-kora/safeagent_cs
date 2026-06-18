from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.services.logging_service import LoggingService


SENSITIVE_OR_VOLATILE_KEYS = {
    "authorization",
    "message",
    "parent_run_id",
    "raw_message",
    "request_id",
    "run_id",
    "secret",
    "session_id",
    "source_run_id",
    "system_prompt",
    "token",
}


@dataclass(frozen=True)
class ToolIdempotencyFacts:
    """一次工具调用需要落库的执行事实。

    tool_call_id 表示物理调用，每次调用都不同；idempotency_key 表示逻辑业务动作，
    同一用户、租户、工具和 ActionPlan fingerprint 应保持稳定。
    """

    tool_call_id: str
    idempotency_key: str
    action_fingerprint: str


def build_action_fingerprint(action_plan: Any) -> str:
    """基于 ActionPlan 或 dict 生成稳定 fingerprint。

    fingerprint 只保存 hash，不保存原始参数。生成前会做 canonical JSON、
    脱敏和易变字段剔除，避免把原始 message、token、secret、api_key 等内容
    纳入事实源。
    """
    payload = _normalize_action_plan(action_plan)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return f"af_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def build_idempotency_key(
    *,
    tenant_id: str | None,
    user_id: str,
    tool_name: str,
    action_fingerprint: str,
) -> str:
    """生成稳定逻辑幂等键。"""
    canonical = json.dumps(
        {
            "tenant_id": tenant_id or "",
            "user_id": user_id,
            "tool_name": tool_name,
            "action_fingerprint": action_fingerprint,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"idem_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def generate_tool_call_id() -> str:
    """生成一次物理工具调用 ID。"""
    return f"tc_{uuid4().hex}"


def build_tool_idempotency_facts(
    *,
    tenant_id: str | None,
    user_id: str,
    tool_name: str,
    action_plan: Any,
) -> ToolIdempotencyFacts:
    action_fingerprint = build_action_fingerprint(action_plan)
    return ToolIdempotencyFacts(
        tool_call_id=generate_tool_call_id(),
        idempotency_key=build_idempotency_key(
            tenant_id=tenant_id,
            user_id=user_id,
            tool_name=tool_name,
            action_fingerprint=action_fingerprint,
        ),
        action_fingerprint=action_fingerprint,
    )


def _normalize_action_plan(action_plan: Any) -> Any:
    if hasattr(action_plan, "to_dict"):
        action_plan = action_plan.to_dict()
    sanitized = LoggingService.sanitize_payload(action_plan)
    return _drop_sensitive_or_volatile_values(sanitized)


def _drop_sensitive_or_volatile_values(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _should_drop_key(key_text):
                continue
            normalized[key_text] = _drop_sensitive_or_volatile_values(item)
        return normalized
    if isinstance(value, list):
        return [_drop_sensitive_or_volatile_values(item) for item in value]
    if isinstance(value, tuple):
        return [_drop_sensitive_or_volatile_values(item) for item in value]
    return value


def _should_drop_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SENSITIVE_OR_VOLATILE_KEYS)
