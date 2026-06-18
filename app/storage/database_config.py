import os
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


DB_BACKEND_SQLITE = "sqlite"
DB_BACKEND_POSTGRES = "postgres"
VALID_DB_BACKENDS = {DB_BACKEND_SQLITE, DB_BACKEND_POSTGRES}


@dataclass(frozen=True)
class DatabaseSettings:
    """数据层运行配置。

    v0.6 默认仍使用 SQLite，PostgreSQL 只作为可选后端。非法 backend 回退
    SQLite，避免因为环境变量拼写错误导致本地测试误连外部数据库。
    """

    backend: str = DB_BACKEND_SQLITE
    database_url: str | None = None


class PostgresConfigurationError(RuntimeError):
    """PostgreSQL 后端配置不完整时抛出的明确异常。"""


def get_database_settings() -> DatabaseSettings:
    backend = os.getenv("SAFEAGENT_DB_BACKEND", DB_BACKEND_SQLITE).strip().lower()
    if backend not in VALID_DB_BACKENDS:
        backend = DB_BACKEND_SQLITE
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
