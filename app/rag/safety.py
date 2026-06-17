import re
from typing import Any

from app.services.logging_service import LoggingService


SENSITIVE_TEXT_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|token)\s*[:=]?\s*[\w.-]*"),
    re.compile(r"(?i)system prompt"),
    re.compile(r"系统提示词"),
    re.compile(r"(?i)traceback"),
    re.compile(r"(?i)stack trace"),
    re.compile(r"内部异常栈"),
    re.compile(r"\b1[3-9]\d{9}\b"),
    re.compile(r"\b\d{17}[\dXx]\b"),
    re.compile(r"\b\d{16,19}\b"),
)


def sanitize_rag_payload(value: Any) -> Any:
    """RAG 输出安全过滤。

    先复用 LoggingService 的通用脱敏，再补充系统提示词、异常栈、
    身份证和银行卡等 RAG 输出禁止项。
    """
    sanitized = LoggingService.sanitize_payload(value)
    return _sanitize_sensitive_text(sanitized)


def _sanitize_sensitive_text(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_sensitive_text(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_sensitive_text(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_sensitive_text(item) for item in value)
    if isinstance(value, str):
        result = value
        for pattern in SENSITIVE_TEXT_PATTERNS:
            result = pattern.sub("***", result)
        return result
    return value

