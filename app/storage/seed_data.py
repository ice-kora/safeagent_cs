from pathlib import Path
from typing import Any

from app.storage.db import get_connection, init_db


SEED_USERS: list[dict[str, Any]] = [
    {
        "id": "u_1001",
        "role": "customer",
        "tenant_id": "t_001",
        "status": "ACTIVE",
    },
    {
        "id": "u_1002",
        "role": "customer",
        "tenant_id": "t_001",
        "status": "ACTIVE",
    },
    {
        "id": "u_1003",
        "role": "customer",
        "tenant_id": "t_001",
        "status": "FROZEN",
    },
    {
        "id": "u_2001",
        "role": "customer",
        "tenant_id": "t_002",
        "status": "ACTIVE",
    },
    {
        "id": "u_2002",
        "role": "customer",
        "tenant_id": "t_002",
        "status": "ACTIVE",
    },
]

SEED_ORDERS: list[dict[str, Any]] = [
    {
        "id": "O10085",
        "user_id": "u_1001",
        "tenant_id": "t_001",
        "status": "PENDING_PAYMENT",
        "delivery_status": "NOT_SHIPPED",
        "refund_status": "NONE",
    },
    {
        "id": "O10086",
        "user_id": "u_1001",
        "tenant_id": "t_001",
        "status": "PAID",
        "delivery_status": "PENDING_SHIPMENT",
        "refund_status": "NONE",
    },
    {
        "id": "O10087",
        "user_id": "u_1002",
        "tenant_id": "t_001",
        "status": "SHIPPED",
        "delivery_status": "SHIPPED",
        "refund_status": "NONE",
    },
    {
        "id": "O10088",
        "user_id": "u_1001",
        "tenant_id": "t_001",
        "status": "COMPLETED",
        "delivery_status": "DELIVERED",
        "refund_status": "NONE",
    },
    {
        "id": "O10089",
        "user_id": "u_1002",
        "tenant_id": "t_001",
        "status": "CANCELLED",
        "delivery_status": "NOT_SHIPPED",
        "refund_status": "NONE",
    },
    {
        "id": "O10090",
        "user_id": "u_1002",
        "tenant_id": "t_001",
        "status": "AFTER_SALES",
        "delivery_status": "DELIVERED",
        "refund_status": "PROCESSING",
    },
    {
        "id": "O10091",
        "user_id": "u_1003",
        "tenant_id": "t_001",
        "status": "PAID",
        "delivery_status": "PENDING_SHIPMENT",
        "refund_status": "NONE",
    },
    {
        "id": "O20001",
        "user_id": "u_2001",
        "tenant_id": "t_002",
        "status": "PAID",
        "delivery_status": "PENDING_SHIPMENT",
        "refund_status": "NONE",
    },
    {
        "id": "O20002",
        "user_id": "u_2002",
        "tenant_id": "t_002",
        "status": "SHIPPED",
        "delivery_status": "SHIPPED",
        "refund_status": "NONE",
    },
]


def seed_sqlite_users_orders(db_path: str | Path | None = None) -> None:
    """向 SQLite 注入最小权限上下文种子数据。

    这里只写 users / orders 的最小字段，不写手机号、地址、支付信息。使用
    INSERT OR IGNORE 保证重复执行不会制造重复数据。
    """
    init_db(db_path)
    with get_connection(db_path) as connection:
        connection.executemany(
            """
            INSERT OR IGNORE INTO users (
                id, role, tenant_id, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
        connection.executemany(
            """
            INSERT OR IGNORE INTO orders (
                id, user_id, tenant_id, status, delivery_status, refund_status,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
