from typing import Any

from app.storage.database_config import PostgresConfigurationError
from app.storage.seed_data import SEED_ORDERS, SEED_USERS


POSTGRES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    role TEXT,
    tenant_id TEXT,
    status TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    status TEXT,
    delivery_status TEXT,
    refund_status TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_users_tenant_id
    ON users(tenant_id);

CREATE INDEX IF NOT EXISTS idx_orders_user_tenant
    ON orders(user_id, tenant_id);
"""


class PostgresBackendError(RuntimeError):
    """PostgreSQL 后端不可用时的明确异常。"""


class PostgresBackend:
    """最小 PostgreSQL 后端。

    本类只承载 users / orders 权限预检上下文，不保存或返回完整订单、
    手机号、地址、支付信息。psycopg 使用延迟导入，保证默认 SQLite 环境
    不会因为未安装 PostgreSQL 驱动而失败。
    """

    def __init__(self, database_url: str | None) -> None:
        if not database_url:
            raise PostgresConfigurationError(
                "SAFEAGENT_DB_BACKEND=postgres requires DATABASE_URL"
            )
        self.database_url = database_url

    def init_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(POSTGRES_SCHEMA_SQL)
            connection.commit()

    def seed_users_orders(self) -> None:
        """幂等写入 PostgreSQL users / orders 种子数据。"""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO users (
                        id, role, tenant_id, status, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (id) DO UPDATE SET
                        role = EXCLUDED.role,
                        tenant_id = EXCLUDED.tenant_id,
                        status = EXCLUDED.status,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    [
                        (
                            user["id"],
                            user["role"],
                            user["tenant_id"],
                            user["status"],
                        )
                        for user in SEED_USERS
                    ],
                )
                cursor.executemany(
                    """
                    INSERT INTO orders (
                        id, user_id, tenant_id, status, delivery_status,
                        refund_status, created_at, updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        tenant_id = EXCLUDED.tenant_id,
                        status = EXCLUDED.status,
                        delivery_status = EXCLUDED.delivery_status,
                        refund_status = EXCLUDED.refund_status,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    [
                        (
                            order["id"],
                            order["user_id"],
                            order["tenant_id"],
                            order["status"],
                            order["delivery_status"],
                            order["refund_status"],
                        )
                        for order in SEED_ORDERS
                    ],
                )
            connection.commit()

    def get_user_context(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, role, tenant_id, status
                    FROM users
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (user_id,),
                )
                row = cursor.fetchone()
        if not row:
            return None
        return {
            "user_id": row[0],
            "role": row[1],
            "tenant_id": row[2],
            "status": row[3],
        }

    def get_order_auth_context(self, order_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, user_id, tenant_id, status, delivery_status,
                           refund_status
                    FROM orders
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (order_id,),
                )
                row = cursor.fetchone()
        if not row:
            return None
        return {
            "order_id": row[0],
            "user_id": row[1],
            "tenant_id": row[2],
            "order_status": row[3],
            "delivery_status": row[4],
            "refund_status": row[5],
        }

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise PostgresBackendError(
                "PostgreSQL backend requires optional dependency psycopg"
            ) from exc
        return psycopg.connect(self.database_url, connect_timeout=10)
