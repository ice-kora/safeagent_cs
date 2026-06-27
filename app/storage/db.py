import sqlite3
from pathlib import Path

from app.storage.models import SCHEMA_SQL


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "safeagent.db"


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path: str | Path | None = None) -> Path:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection(path) as connection:
        connection.executescript(SCHEMA_SQL)
        _ensure_tool_call_log_columns(connection)
        _ensure_policy_log_columns(connection)
        connection.commit()
    return path


def _ensure_tool_call_log_columns(connection: sqlite3.Connection) -> None:
    """为已存在的 SQLite 数据库补齐 v0.4A 新字段。

    CREATE TABLE IF NOT EXISTS 不会修改旧表结构，所以这里用轻量迁移保证
    旧本地数据库也能写入 tool_call_id / idempotency_key / action_fingerprint。
    """
    rows = connection.execute("PRAGMA table_info(tool_call_logs)").fetchall()
    existing_columns = {row["name"] for row in rows}
    migrations = {
        "tool_call_id": "ALTER TABLE tool_call_logs ADD COLUMN tool_call_id TEXT",
        "idempotency_key": "ALTER TABLE tool_call_logs ADD COLUMN idempotency_key TEXT",
        "action_fingerprint": "ALTER TABLE tool_call_logs ADD COLUMN action_fingerprint TEXT",
    }
    for column, sql in migrations.items():
        if column not in existing_columns:
            connection.execute(sql)
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tool_call_logs_tool_call_id
            ON tool_call_logs(tool_call_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tool_call_logs_idempotency_key
            ON tool_call_logs(idempotency_key)
        """
    )


def _ensure_policy_log_columns(connection: sqlite3.Connection) -> None:
    """为已存在的 SQLite 数据库补齐 v0.8 policy audit 字段。"""
    rows = connection.execute("PRAGMA table_info(policy_logs)").fetchall()
    existing_columns = {row["name"] for row in rows}
    migrations = {
        "request_id": "ALTER TABLE policy_logs ADD COLUMN request_id TEXT",
        "tool_name": "ALTER TABLE policy_logs ADD COLUMN tool_name TEXT",
        "code": "ALTER TABLE policy_logs ADD COLUMN code TEXT",
    }
    for column, sql in migrations.items():
        if column not in existing_columns:
            connection.execute(sql)
