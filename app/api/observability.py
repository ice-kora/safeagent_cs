import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.services.logging_service import LoggingService
from app.storage.runtime_store import RuntimeStore, get_runtime_store


router = APIRouter()

CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
SYSTEM_PROMPT_PATTERN = re.compile(
    r"(?is)\bsystem\s*prompt\s*[:=]\s*.+",
)
ADDRESS_TEXT_PATTERN = re.compile(
    r"(?i)(收货地址|详细地址|"
    r"\b\d{1,6}\s+[\w\s.-]+(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr)\b|"
    r"[\u4e00-\u9fff]{2,}(?:省|市|区|县|路|街|号|室))"
)
SENSITIVE_OBSERVABILITY_KEYS = {
    "developer_prompt",
    "instruction_prompt",
    "prompt_template",
    "system",
    "system_message",
    "system_prompt",
}


def get_observability_runtime_store() -> RuntimeStore:
    return get_runtime_store()


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    store: RuntimeStore = Depends(get_observability_runtime_store),
) -> dict[str, Any]:
    run = store.get_agent_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return _sanitize_payload(run)


@router.get("/runs/{run_id}/traces")
def get_run_traces(
    run_id: str,
    store: RuntimeStore = Depends(get_observability_runtime_store),
) -> list[dict[str, Any]]:
    traces = [_normalize_trace(row) for row in store.list_agent_traces(run_id)]
    return _sanitize_payload(traces)


@router.get("/runs/{run_id}/tool-calls")
def get_run_tool_calls(
    run_id: str,
    store: RuntimeStore = Depends(get_observability_runtime_store),
) -> list[dict[str, Any]]:
    logs = [_normalize_tool_call(row) for row in store.list_tool_call_logs(run_id)]
    return _sanitize_payload(logs)


@router.get("/runs/{run_id}/policy-logs")
def get_run_policy_logs(
    run_id: str,
    store: RuntimeStore = Depends(get_observability_runtime_store),
) -> list[dict[str, Any]]:
    return _sanitize_payload(store.list_policy_logs(run_id))


@router.get("/runs/{run_id}/failure-logs")
def get_run_failure_logs(
    run_id: str,
    store: RuntimeStore = Depends(get_observability_runtime_store),
) -> list[dict[str, Any]]:
    return _sanitize_payload(store.list_failure_logs(run_id))


@router.get("/pending-actions")
def get_pending_actions(
    user_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    store: RuntimeStore = Depends(get_observability_runtime_store),
) -> list[dict[str, Any]]:
    actions = [
        _normalize_pending_action(row)
        for row in store.list_pending_actions(user_id=user_id, session_id=session_id)
    ]
    return _sanitize_payload(actions)


def _normalize_trace(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["input"] = _decode_json(normalized.pop("input_json", None))
    normalized["output"] = _decode_json(normalized.pop("output_json", None))
    return normalized


def _normalize_tool_call(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["tool_args"] = _decode_json(normalized.pop("tool_args_json", None))
    normalized["tool_result_summary"] = _decode_json(
        normalized.pop("tool_result_summary_json", None)
    )
    return normalized


def _normalize_pending_action(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["action_plan"] = _decode_json(normalized.pop("action_plan_json", None))
    return normalized


def _decode_json(value: Any) -> Any:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _sanitize_payload(value: Any) -> Any:
    sanitized = LoggingService.sanitize_payload(value)
    return _sanitize_observability_payload(sanitized)


def _sanitize_observability_payload(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_OBSERVABILITY_KEYS:
                result[key] = "***"
            else:
                result[key] = _sanitize_observability_payload(item)
        return result
    if isinstance(value, list):
        return [_sanitize_observability_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_observability_payload(item) for item in value)
    if isinstance(value, str):
        value = CARD_PATTERN.sub("***", value)
        value = SYSTEM_PROMPT_PATTERN.sub("system_prompt=***", value)
        if ADDRESS_TEXT_PATTERN.search(value):
            return "***"
    return value
