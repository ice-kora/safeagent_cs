import os
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from app.core.env import load_env_files
from app.core.profiles import get_active_profile, get_profile_defaults


DB_BACKEND_SQLITE = "sqlite"
DB_BACKEND_POSTGRES = "postgres"
VALID_DB_BACKENDS = {DB_BACKEND_SQLITE, DB_BACKEND_POSTGRES}


@dataclass(frozen=True)
class DatabaseSettings:
    """数据层运行配置。

    dev profile 默认 SQLite；demo/prod profile 默认 PostgreSQL。非法 backend
    回退当前 profile 默认值，测试环境未设置 profile 时仍保持 SQLite。
    """

    backend: str = DB_BACKEND_SQLITE
    database_url: str | None = None


class PostgresConfigurationError(RuntimeError):
    """PostgreSQL 后端配置不完整时抛出的明确异常。"""


def get_database_settings() -> DatabaseSettings:
    load_env_files()
    defaults = get_profile_defaults(get_active_profile())
    backend = os.getenv("SAFEAGENT_DB_BACKEND", defaults.db_backend).strip().lower()
    if backend not in VALID_DB_BACKENDS:
        backend = defaults.db_backend
    return DatabaseSettings(
        backend=backend,
        database_url=os.getenv("DATABASE_URL"),
    )


def redact_database_url(database_url: str | None) -> str | None:
    """返回可安全打印的 DATABASE_URL，不泄露密码。"""
    if not database_url:
        return database_url
    parsed = urlsplit(database_url)
    if not parsed.password:
        return database_url

    username = parsed.username or ""
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    safe_netloc = f"{username}:***@{hostname}{port}"
    return urlunsplit(
        (parsed.scheme, safe_netloc, parsed.path, parsed.query, parsed.fragment)
    )
