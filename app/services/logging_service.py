import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_PATH = PROJECT_ROOT / "logs" / "application.log"

SENSITIVE_KEYS = {
    "address",
    "address_full",
    "api_key",
    "authorization",
    "card",
    "id_card",
    "password",
    "payment",
    "payment_info",
    "phone",
    "secret",
    "system_prompt",
    "token",
}

# 日志脱敏采用两层策略：
# 1. 命中敏感字段名时整体替换；
# 2. 普通字符串里再识别手机号、token 等模式。
# 这样可以降低误把敏感数据写入 application.log 的风险。
PHONE_PATTERN = re.compile(r"\b1[3-9]\d{9}\b")
TOKEN_PATTERN = re.compile(r"(?i)\b(api[_-]?key|token|secret)\s*[:=]\s*[\w.-]+")


class LoggingService:
    """应用结构化日志服务。

    业务模块不应直接 print。统一通过 LoggingService 写 JSON 行日志，
    便于后续排障、审计扩展，以及统一做敏感字段脱敏。
    """

    def __init__(self, log_path: str | Path | None = None) -> None:
        configured_log_path = log_path or os.getenv("SAFEAGENT_LOG_PATH")
        self.log_path = Path(configured_log_path) if configured_log_path else DEFAULT_LOG_PATH
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        logger_name = f"safeagent.{self.log_path.resolve()}"
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        if not self.logger.handlers:
            handler = self._build_file_handler(self.log_path)
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)

    def info(self, event: str, payload: dict[str, Any]) -> None:
        """写入普通信息日志。"""
        self._write("INFO", event, payload)

    def warning(self, event: str, payload: dict[str, Any]) -> None:
        self._write("WARNING", event, payload)

    def error(self, event: str, payload: dict[str, Any]) -> None:
        self._write("ERROR", event, payload)

    def security(self, event: str, payload: dict[str, Any]) -> None:
        """写入安全相关日志，后续可升级为 security_logs 的统一入口。"""
        self._write("SECURITY", event, payload)

    def _build_file_handler(self, log_path: Path) -> logging.FileHandler:
        try:
            return logging.FileHandler(log_path, encoding="utf-8")
        except PermissionError:
            fallback_path = Path(tempfile.gettempdir()) / "safeagent-cs" / "application.log"
            fallback_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path = fallback_path
            return logging.FileHandler(fallback_path, encoding="utf-8")

    def _write(self, level: str, event: str, payload: dict[str, Any]) -> None:
        record = {
            "level": level,
            "event": event,
            "payload": self.sanitize_payload(payload),
        }
        line = json.dumps(record, ensure_ascii=False, default=str)
        if level in {"ERROR", "SECURITY"}:
            self.logger.error(line)
        elif level == "WARNING":
            self.logger.warning(line)
        else:
            self.logger.info(line)

    @classmethod
    def sanitize_payload(cls, value: Any) -> Any:
        """递归脱敏日志载荷。

        Trace、工具日志和应用日志都可能复用该方法，所以这里保持通用：
        支持 dict/list/tuple/string，避免嵌套结构里的敏感字段漏出。
        """
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                if cls._is_sensitive_key(str(key)):
                    sanitized[key] = "***"
                else:
                    sanitized[key] = cls.sanitize_payload(item)
            return sanitized
        if isinstance(value, list):
            return [cls.sanitize_payload(item) for item in value]
        if isinstance(value, tuple):
            return tuple(cls.sanitize_payload(item) for item in value)
        if isinstance(value, str):
            return cls._sanitize_string(value)
        return value

    @staticmethod
    def _is_sensitive_key(key: str) -> bool:
        lowered = key.lower()
        return any(sensitive in lowered for sensitive in SENSITIVE_KEYS)

    @staticmethod
    def _sanitize_string(value: str) -> str:
        value = PHONE_PATTERN.sub("***", value)
        value = TOKEN_PATTERN.sub(lambda match: f"{match.group(1)}=***", value)
        return value
