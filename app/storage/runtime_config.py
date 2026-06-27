import os
from dataclasses import dataclass

from app.core.env import load_env_files
from app.core.profiles import get_active_profile, get_profile_defaults
from app.storage.database_config import (
    DB_BACKEND_POSTGRES,
    DB_BACKEND_SQLITE,
    redact_database_url,
)


RUNTIME_BACKEND_SQLITE = DB_BACKEND_SQLITE
RUNTIME_BACKEND_POSTGRES = DB_BACKEND_POSTGRES
VALID_RUNTIME_BACKENDS = {RUNTIME_BACKEND_SQLITE, RUNTIME_BACKEND_POSTGRES}


@dataclass(frozen=True)
class RuntimeDatabaseSettings:
    """Runtime Store 后端配置。

    Runtime Store 承载 agent_runs、traces、tickets、pending_actions、工具日志、
    失败日志等运行时数据。dev profile 默认 SQLite；demo/prod profile 默认
    PostgreSQL。测试环境未设置 profile 时仍保持 SQLite。
    """

    backend: str = RUNTIME_BACKEND_SQLITE
    database_url: str | None = None


class RuntimePostgresConfigurationError(RuntimeError):
    """Runtime PostgreSQL 配置缺失时抛出的明确异常。"""


def get_runtime_database_settings() -> RuntimeDatabaseSettings:
    load_env_files()
    defaults = get_profile_defaults(get_active_profile())
    backend = os.getenv(
        "SAFEAGENT_RUNTIME_BACKEND",
        defaults.runtime_backend,
    ).strip().lower()
    if backend not in VALID_RUNTIME_BACKENDS:
        backend = defaults.runtime_backend

    runtime_url = os.getenv("SAFEAGENT_RUNTIME_DATABASE_URL") or os.getenv(
        "DATABASE_URL"
    )
    return RuntimeDatabaseSettings(
        backend=backend,
        database_url=runtime_url,
    )


def redact_runtime_database_url(database_url: str | None) -> str | None:
    """复用 platform data 的 URL 脱敏逻辑。"""
    return redact_database_url(database_url)
