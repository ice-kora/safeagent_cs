"""PostgreSQL seed 入口 —— 最小、可重复执行。

用法：
    python seed_postgres.py

前置条件：
    SAFEAGENT_DB_BACKEND=postgres
    DATABASE_URL=postgresql://safeagent:safeagent_pwd@localhost:5432/safeagent_cs

每次运行都会幂等执行 init_schema + seed_users_orders，
不会产生重复数据（ON CONFLICT DO NOTHING）。
"""

from app.storage.database_config import (
    DB_BACKEND_POSTGRES,
    get_database_settings,
    redact_database_url,
)
from app.storage.postgres import PostgresBackend


def main() -> None:
    settings = get_database_settings()
    if settings.backend != DB_BACKEND_POSTGRES:
        print(
            f"[ERROR] SAFEAGENT_DB_BACKEND is '{settings.backend}', "
            f"need '{DB_BACKEND_POSTGRES}'"
        )
        return

    if not settings.database_url:
        print("[ERROR] DATABASE_URL is not set")
        return

    print(f"[connect] PostgreSQL: {redact_database_url(settings.database_url)}")
    backend = PostgresBackend(settings.database_url)

    print("[init] schema ...")
    backend.init_schema()
    print("   OK - schema ready (CREATE TABLE IF NOT EXISTS)")

    print("[seed] users / orders ...")
    backend.seed_users_orders()
    print("   OK - seed done (ON CONFLICT DO NOTHING, idempotent)")

    # verify
    user = backend.get_user_context("u_1001")
    order = backend.get_order_auth_context("O10086")
    print(f"\n[verify] seed result:")
    print(f"   user u_1001: {user}")
    print(f"   order O10086: {order}")

    if user and order:
        print("\n[OK] PostgreSQL seed completed.")
    else:
        print("\n[WARN] verification failed, please check.")


if __name__ == "__main__":
    main()
