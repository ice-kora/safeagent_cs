import json
from pathlib import Path
from typing import Any

from app.storage.database_config import (
    DB_BACKEND_POSTGRES,
    DB_BACKEND_SQLITE,
    get_database_settings,
)
from app.storage.db import DEFAULT_DB_PATH, get_connection, init_db
from app.storage.postgres import PostgresBackend


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


class RepositoryService:
    """只读权限预检仓储。

    PolicyService 后续需要判断“资源是否属于当前用户”，但又不能调用业务工具。
    RepositoryService 提供最小权限上下文，避免把完整订单、地址、手机号、
    支付信息等敏感数据提前暴露给 Agent 流程。

    P0 身份语义说明：
    - 客户不是商家，客户是发起咨询的买家。
    - 商家是租户，订单归属于某个 merchant_tenant_id。
    - 客服是操作人员，support_agent_id / actor_id / actor_role 暂不实现。
    - Mock 字段名仍保留 user_id / tenant_id，但语义分别是
      customer_user_id / merchant_tenant_id。
    """

    def __init__(
        self,
        mock_dir: str | Path | None = None,
        db_path: str | Path | None = None,
        db_backend: str | None = None,
        database_url: str | None = None,
    ) -> None:
        self.mock_dir = Path(mock_dir) if mock_dir else DEFAULT_MOCK_DIR
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        settings = get_database_settings()
        selected_backend = (db_backend or settings.backend).strip().lower()
        if selected_backend not in {DB_BACKEND_SQLITE, DB_BACKEND_POSTGRES}:
            selected_backend = DB_BACKEND_SQLITE
        self.db_backend = selected_backend
        self.database_url = database_url or settings.database_url
        self.postgres_backend: PostgresBackend | None = None

        # v0.6-DB-R1: 始终初始化 runtime SQLite store（tickets 等运行时表），
        # 即使 platform data（users / orders）走 PostgreSQL 也不能跳过。
        init_db(self.db_path)

        if self.db_backend == DB_BACKEND_POSTGRES:
            self.postgres_backend = PostgresBackend(self.database_url)
            self.postgres_backend.init_schema()

    def get_user_context(self, user_id: str) -> dict[str, Any] | None:
        """读取客户最小上下文，只返回权限判断需要的字段。

        返回的 role 字段暂时不参与 P0 裁决，但保留给后续客服角色权限扩展。
        tenant_id 在 P0 中表示当前客服入口所属商家，即 session_tenant_id。
        v0.4B 要求字段稳定为 user_id / tenant_id / role / status。
        """
        user = self._get_user_context_from_db(user_id)
        if user:
            return user

        user = self._find_by_id("mock_users.json", user_id)
        if not user:
            return None
        return {
            "user_id": user["id"],
            "role": user.get("role"),
            "tenant_id": user.get("tenant_id"),
            "status": user.get("status"),
        }

    def get_order_auth_context(self, order_id: str) -> dict[str, Any] | None:
        """读取订单权限上下文，不返回完整订单对象。

        这里刻意不返回 amount、address、phone、payment_info。
        后续真正订单详情只能通过 ToolGateway 调用工具，并且结果必须脱敏。
        返回的 user_id 表示订单所属客户 customer_user_id；
        返回的 tenant_id 表示订单所属商家 merchant_tenant_id。
        """
        order = self._get_order_auth_context_from_db(order_id)
        if order:
            return order

        order = self._find_by_id("mock_orders.json", order_id)
        if not order:
            return None
        return {
            "order_id": order["id"],
            "user_id": order.get("user_id"),
            "tenant_id": order.get("tenant_id"),
            "order_status": order.get("status"),
            "delivery_status": order.get("delivery_status"),
            "refund_status": order.get("refund_status"),
        }

    def get_open_ticket_by_idempotency_key(
        self, idempotency_key: str
    ) -> dict[str, Any] | None:
        """查询同一幂等键下未关闭工单，用于避免重复创建人工工单。"""
        query = """
            SELECT id, user_id, type, status, risk_level, idempotency_key,
                   source_run_id, parent_run_id, pending_action_id
            FROM tickets
            WHERE idempotency_key = ?
              AND status IN ('OPEN', 'PROCESSING')
            ORDER BY created_at DESC
            LIMIT 1
        """
        with get_connection(self.db_path) as connection:
            row = connection.execute(query, (idempotency_key,)).fetchone()
        return dict(row) if row else None

    def _get_user_context_from_db(self, user_id: str) -> dict[str, Any] | None:
        if self.db_backend == DB_BACKEND_POSTGRES:
            if not self.postgres_backend:
                return None
            return self.postgres_backend.get_user_context(user_id)

        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT id, role, tenant_id, status
                FROM users
                WHERE id = ?
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "user_id": row["id"],
            "role": row["role"],
            "tenant_id": row["tenant_id"],
            "status": row["status"],
        }

    def _get_order_auth_context_from_db(self, order_id: str) -> dict[str, Any] | None:
        if self.db_backend == DB_BACKEND_POSTGRES:
            if not self.postgres_backend:
                return None
            return self.postgres_backend.get_order_auth_context(order_id)

        with get_connection(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT id, user_id, tenant_id, status, delivery_status, refund_status
                FROM orders
                WHERE id = ?
                LIMIT 1
                """,
                (order_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "order_id": row["id"],
            "user_id": row["user_id"],
            "tenant_id": row["tenant_id"],
            "order_status": row["status"],
            "delivery_status": row["delivery_status"],
            "refund_status": row["refund_status"],
        }

    def _find_by_id(self, file_name: str, item_id: str) -> dict[str, Any] | None:
        for item in self._load_json_list(file_name):
            if item.get("id") == item_id:
                return item
        return None

    def _load_json_list(self, file_name: str) -> list[dict[str, Any]]:
        path = self.mock_dir / file_name
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError:
            raise RuntimeError(f"Mock data file not found: {path}") from None
        if not isinstance(data, list):
            raise ValueError(f"{file_name} must contain a JSON list")
        return data
