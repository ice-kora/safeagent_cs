"""v0.6-DB-R1: Platform Data 与 Runtime Store 边界测试。

验证：
- postgres mode 下 runtime SQLite tickets 表存在
- postgres mode 下 get_open_ticket_by_idempotency_key 不因缺表失败
- postgres mode 下 users/orders 仍从 PG 读取
- get_open_ticket_by_idempotency_key 找不到时返回 None
- PolicyService request_refund 不因 tickets 表缺失而失败
"""

import os
from pathlib import Path

import pytest

from app.core.constants import PolicyDecisionType
from app.core.risk import RiskLevel
from app.services.planner_service import RuleBasedActionPlanner
from app.services.policy_service import PolicyService
from app.services.repository_service import RepositoryService
from app.storage.database_config import DB_BACKEND_POSTGRES, DB_BACKEND_SQLITE
from app.storage.db import get_connection


# ── 辅助函数 ──────────────────────────────────────────────────────────


def _tickets_table_exists(db_path: Path) -> bool:
    """检查 SQLite db 中 tickets 表是否存在。"""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='tickets'
            """
        ).fetchall()
    return len(rows) > 0


# ── 边界测试 1: postgres mode 下 runtime SQLite 表存在 ──────────────


def test_runtime_sqlite_tickets_table_exists_in_postgres_mode(
    tmp_path: Path, monkeypatch
) -> None:
    """SAFEAGENT_DB_BACKEND=postgres 时，RepositoryService 初始化后
    runtime SQLite tickets 表必须存在。"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is not configured")

    monkeypatch.setenv("SAFEAGENT_DB_BACKEND", DB_BACKEND_POSTGRES)
    monkeypatch.setenv("DATABASE_URL", database_url)

    db_path = tmp_path / "test_runtime.db"
    RepositoryService(db_path=db_path)

    assert _tickets_table_exists(db_path), (
        "postgres mode 下 runtime SQLite tickets 表必须存在"
    )


def test_runtime_sqlite_tickets_table_exists_in_sqlite_mode(
    tmp_path: Path, monkeypatch
) -> None:
    """SAFEAGENT_DB_BACKEND=sqlite（默认）时，tickets 表也存在。"""
    monkeypatch.delenv("SAFEAGENT_DB_BACKEND", raising=False)

    db_path = tmp_path / "test_runtime.db"
    RepositoryService(db_path=db_path)

    assert _tickets_table_exists(db_path), (
        "sqlite mode 下 runtime tickets 表必须存在"
    )


# ── 边界测试 2: get_open_ticket_by_idempotency_key 不因缺表失败 ────


def test_get_open_ticket_does_not_fail_in_postgres_mode(
    tmp_path: Path, monkeypatch
) -> None:
    """postgres mode 下 get_open_ticket_by_idempotency_key 不因
    tickets 表缺失而抛出异常。"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is not configured")

    monkeypatch.setenv("SAFEAGENT_DB_BACKEND", DB_BACKEND_POSTGRES)
    monkeypatch.setenv("DATABASE_URL", database_url)

    db_path = tmp_path / "test_runtime.db"
    repository = RepositoryService(db_path=db_path)

    # 不应抛出异常
    result = repository.get_open_ticket_by_idempotency_key(
        "u_1001:request_refund:order:O10086"
    )
    # 空表情况下应返回 None
    assert result is None


# ── 边界测试 3: postgres mode 下 users/orders 从 PG 读取 ────────────


def test_users_read_from_pg_in_postgres_mode(tmp_path: Path, monkeypatch) -> None:
    """postgres mode 下 get_user_context 优先从 PG 读取。"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is not configured")

    monkeypatch.setenv("SAFEAGENT_DB_BACKEND", DB_BACKEND_POSTGRES)
    monkeypatch.setenv("DATABASE_URL", database_url)

    db_path = tmp_path / "test_runtime.db"
    repository = RepositoryService(db_path=db_path)

    user = repository.get_user_context("u_1001")
    assert user is not None
    assert user["user_id"] == "u_1001"
    assert user["role"] == "customer"
    assert user["tenant_id"] == "t_001"
    assert user["status"] == "ACTIVE"


def test_orders_read_from_pg_in_postgres_mode(tmp_path: Path, monkeypatch) -> None:
    """postgres mode 下 get_order_auth_context 优先从 PG 读取。"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is not configured")

    monkeypatch.setenv("SAFEAGENT_DB_BACKEND", DB_BACKEND_POSTGRES)
    monkeypatch.setenv("DATABASE_URL", database_url)

    db_path = tmp_path / "test_runtime.db"
    repository = RepositoryService(db_path=db_path)

    order = repository.get_order_auth_context("O10086")
    assert order is not None
    assert order["order_id"] == "O10086"
    assert order["user_id"] == "u_1001"
    assert order["tenant_id"] == "t_001"
    assert order["order_status"] == "PAID"


# ── 边界测试 4: get_open_ticket_by_idempotency_key 找不到时返回 None ─


def test_get_open_ticket_returns_none_for_unknown_key(
    tmp_path: Path, monkeypatch
) -> None:
    """不存在的幂等键应返回 None。"""
    monkeypatch.delenv("SAFEAGENT_DB_BACKEND", raising=False)

    db_path = tmp_path / "test_runtime.db"
    repository = RepositoryService(db_path=db_path)

    result = repository.get_open_ticket_by_idempotency_key("nonexistent_key")
    assert result is None


# ── 边界测试 5: PolicyService request_refund 不因缺表失败 ────────────


def test_policy_refund_does_not_fail_in_postgres_mode(
    tmp_path: Path, monkeypatch
) -> None:
    """postgres mode 下 PolicyService.evaluate 处理 refund_request
    不应因 tickets 表缺失而失败。"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is not configured")

    monkeypatch.setenv("SAFEAGENT_DB_BACKEND", DB_BACKEND_POSTGRES)
    monkeypatch.setenv("DATABASE_URL", database_url)

    db_path = tmp_path / "test_runtime.db"
    repository = RepositoryService(db_path=db_path)
    service = PolicyService(repository=repository)

    plan = RuleBasedActionPlanner().plan(
        intent="refund_request",
        message="我要把订单 O10086 退款",
    )

    decision = service.evaluate(plan, customer_user_id="u_1001")

    assert decision.decision == PolicyDecisionType.HUMAN_REQUIRED
    assert decision.risk_level == RiskLevel.L4


# ── 边界测试 6: users/orders 字段不泄露敏感数据 ────────────────────


def test_postgres_mode_returns_minimal_fields(tmp_path: Path, monkeypatch) -> None:
    """postgres mode 下返回字段不含敏感数据。"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is not configured")

    monkeypatch.setenv("SAFEAGENT_DB_BACKEND", DB_BACKEND_POSTGRES)
    monkeypatch.setenv("DATABASE_URL", database_url)

    db_path = tmp_path / "test_runtime.db"
    repository = RepositoryService(db_path=db_path)

    user = repository.get_user_context("u_1001")
    order = repository.get_order_auth_context("O10086")

    assert set(user.keys()) == {"user_id", "role", "tenant_id", "status"}
    assert set(order.keys()) == {
        "order_id",
        "user_id",
        "tenant_id",
        "order_status",
        "delivery_status",
        "refund_status",
    }

    assert "phone" not in str(user)
    assert "address" not in str(order)
    assert "payment" not in str(order)
