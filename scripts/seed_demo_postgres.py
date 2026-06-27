import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.action_plan import ActionPlan
from app.storage.database_config import (
    DB_BACKEND_POSTGRES,
    get_database_settings,
    redact_database_url,
)
from app.storage.postgres import PostgresBackend
from app.storage.runtime_postgres import PostgresRuntimeStore
from app.storage.seed_data import SEED_ORDERS, SEED_USERS


DEMO_TICKETS = [
    {
        "id": "T_DEMO_OPEN_001",
        "user_id": "u_1001",
        "type": "complaint",
        "status": "OPEN",
        "risk_level": "L4",
        "idempotency_key": "idem_demo_complaint_repeat_u1001",
        "source_run_id": "run_demo_ticket_open",
        "description": "用户反馈售后处理较慢，已脱敏。",
    },
    {
        "id": "T_DEMO_PROCESSING_001",
        "user_id": "u_1002",
        "type": "refund",
        "status": "PROCESSING",
        "risk_level": "L3",
        "idempotency_key": "idem_demo_refund_u1002_o10090",
        "source_run_id": "run_demo_ticket_processing",
        "description": "售后中订单退款咨询，已脱敏。",
    },
    {
        "id": "T_DEMO_CLOSED_001",
        "user_id": "u_2001",
        "type": "complaint",
        "status": "CLOSED",
        "risk_level": "L4",
        "idempotency_key": "idem_demo_complaint_closed_u2001",
        "source_run_id": "run_demo_ticket_closed",
        "description": "重复投诉已合并关闭，已脱敏。",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed SafeAgent-CS PostgreSQL demo data")
    parser.add_argument("--reset", action="store_true", help="delete demo rows before seeding")
    args = parser.parse_args()

    settings = get_database_settings()
    if settings.backend != DB_BACKEND_POSTGRES:
        print(
            f"[ERROR] SAFEAGENT_DB_BACKEND is {settings.backend!r}; expected 'postgres'."
        )
        return 1
    if not settings.database_url:
        print("[ERROR] DATABASE_URL is required for PostgreSQL demo seed.")
        return 1

    print(f"[connect] PostgreSQL: {redact_database_url(settings.database_url)}")
    platform = PostgresBackend(settings.database_url)
    platform.init_schema()
    runtime = PostgresRuntimeStore(settings.database_url)
    runtime.init_schema()

    if args.reset:
        with _connect(settings.database_url) as connection:
            _reset_demo_rows(connection)
            connection.commit()

    platform.seed_users_orders()

    with _connect(settings.database_url) as connection:
        _seed_runtime_rows(connection)
        connection.commit()
        counts = _count_demo_rows(connection)

    print("[seed] demo rows upserted")
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    print("[OK] PostgreSQL demo seed completed.")
    return 0


def _reset_demo_rows(connection) -> None:
    demo_ids = _demo_id_sets()
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM checkpoint_events WHERE checkpoint_id = ANY(%s)",
            (demo_ids["checkpoints"],),
        )
        cursor.execute(
            "DELETE FROM resume_attempts WHERE checkpoint_id = ANY(%s)",
            (demo_ids["checkpoints"],),
        )
        cursor.execute(
            "DELETE FROM checkpoints WHERE checkpoint_id = ANY(%s)",
            (demo_ids["checkpoints"],),
        )
        cursor.execute(
            "DELETE FROM pending_action_events WHERE pending_action_id = ANY(%s)",
            (demo_ids["pending_actions"],),
        )
        cursor.execute(
            "DELETE FROM pending_actions WHERE pending_action_id = ANY(%s)",
            (demo_ids["pending_actions"],),
        )
        cursor.execute("DELETE FROM tickets WHERE id = ANY(%s)", (demo_ids["tickets"],))
        cursor.execute("DELETE FROM agent_traces WHERE run_id = ANY(%s)", (demo_ids["runs"],))
        cursor.execute("DELETE FROM agent_runs WHERE run_id = ANY(%s)", (demo_ids["runs"],))
        cursor.execute("DELETE FROM orders WHERE id = ANY(%s)", (demo_ids["orders"],))
        cursor.execute("DELETE FROM users WHERE id = ANY(%s)", (demo_ids["users"],))
    print("[reset] deleted existing demo rows")


def _seed_runtime_rows(connection) -> None:
    now = datetime.now(UTC)
    pending_rows = _pending_action_rows(now)
    checkpoint_rows = _checkpoint_rows(now)
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO agent_runs (
                run_id, session_id, user_id, request_id, parent_run_id,
                pending_action_id, status, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE SET
                status = EXCLUDED.status,
                pending_action_id = EXCLUDED.pending_action_id,
                updated_at = EXCLUDED.updated_at
            """,
            [
                (
                    row["run_id"],
                    row["session_id"],
                    row["user_id"],
                    row["request_id"],
                    None,
                    row.get("pending_action_id"),
                    row["status"],
                    row["created_at"],
                    row["updated_at"],
                )
                for row in _agent_run_rows(now)
            ],
        )
        cursor.executemany(
            """
            INSERT INTO tickets (
                id, user_id, type, status, risk_level, idempotency_key,
                source_run_id, parent_run_id, pending_action_id, description,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                risk_level = EXCLUDED.risk_level,
                description = EXCLUDED.description,
                updated_at = EXCLUDED.updated_at
            """,
            [
                (
                    row["id"],
                    row["user_id"],
                    row["type"],
                    row["status"],
                    row["risk_level"],
                    row["idempotency_key"],
                    row.get("source_run_id"),
                    row.get("parent_run_id"),
                    row.get("pending_action_id"),
                    row.get("description"),
                    now.isoformat(),
                    now.isoformat(),
                )
                for row in DEMO_TICKETS
            ],
        )
        cursor.executemany(
            """
            INSERT INTO pending_actions (
                pending_action_id, session_id, source_run_id, user_id,
                action_plan_json, risk_level, status, expires_at,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (pending_action_id) DO UPDATE SET
                status = EXCLUDED.status,
                expires_at = EXCLUDED.expires_at,
                updated_at = EXCLUDED.updated_at
            """,
            [_pending_values(row) for row in pending_rows],
        )
        cursor.executemany(
            """
            INSERT INTO pending_action_events (
                event_id, pending_action_id, run_id, parent_run_id,
                session_id, user_id, tenant_id, event_type, old_status,
                new_status, reason, metadata_json, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_id) DO NOTHING
            """,
            [_pending_event_values(row, now) for row in pending_rows],
        )
        cursor.executemany(
            """
            INSERT INTO checkpoints (
                checkpoint_id, run_id, parent_run_id, session_id, user_id,
                current_node, checkpoint_type, state_snapshot_json,
                resume_policy_json, status, expires_at, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (checkpoint_id) DO UPDATE SET
                status = EXCLUDED.status,
                expires_at = EXCLUDED.expires_at,
                updated_at = EXCLUDED.updated_at
            """,
            [_checkpoint_values(row) for row in checkpoint_rows],
        )
        cursor.executemany(
            """
            INSERT INTO checkpoint_events (
                event_id, checkpoint_id, run_id, parent_run_id, session_id,
                user_id, event_type, old_status, new_status, reason,
                metadata_json, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_id) DO NOTHING
            """,
            [_checkpoint_event_values(row, now) for row in checkpoint_rows],
        )


def _agent_run_rows(now: datetime) -> list[dict[str, Any]]:
    return [
        {
            "run_id": "run_demo_waiting_confirm",
            "session_id": "sess_demo_001",
            "user_id": "u_1001",
            "request_id": "req_demo_waiting_confirm",
            "pending_action_id": "pa_demo_waiting_confirm",
            "status": "SUCCESS",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        {
            "run_id": "run_demo_cancelled",
            "session_id": "sess_demo_001",
            "user_id": "u_1001",
            "request_id": "req_demo_cancelled",
            "pending_action_id": "pa_demo_cancelled",
            "status": "SUCCESS",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        {
            "run_id": "run_demo_expired",
            "session_id": "sess_demo_002",
            "user_id": "u_1002",
            "request_id": "req_demo_expired",
            "pending_action_id": "pa_demo_expired",
            "status": "FAILED",
            "created_at": (now - timedelta(hours=2)).isoformat(),
            "updated_at": (now - timedelta(hours=2)).isoformat(),
        },
        {
            "run_id": "run_demo_resumable",
            "session_id": "sess_demo_003",
            "user_id": "u_2001",
            "request_id": "req_demo_resumable",
            "pending_action_id": "pa_demo_resumable",
            "status": "SUCCESS",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    ]


def _pending_action_rows(now: datetime) -> list[dict[str, Any]]:
    return [
        _pending_row(
            "pa_demo_waiting_confirm",
            "sess_demo_001",
            "run_demo_waiting_confirm",
            "u_1001",
            "PENDING",
            now + timedelta(minutes=30),
            "O10086",
        ),
        _pending_row(
            "pa_demo_cancelled",
            "sess_demo_001",
            "run_demo_cancelled",
            "u_1001",
            "CANCELLED",
            now + timedelta(minutes=30),
            "O10086",
        ),
        _pending_row(
            "pa_demo_expired",
            "sess_demo_002",
            "run_demo_expired",
            "u_1002",
            "EXPIRED",
            now - timedelta(minutes=30),
            "O10087",
        ),
        _pending_row(
            "pa_demo_resumable",
            "sess_demo_003",
            "run_demo_resumable",
            "u_2001",
            "PENDING",
            now + timedelta(minutes=30),
            "O20001",
        ),
    ]


def _pending_row(
    pending_action_id: str,
    session_id: str,
    run_id: str,
    user_id: str,
    status: str,
    expires_at: datetime,
    order_id: str,
) -> dict[str, Any]:
    plan = ActionPlan(
        intent="address_change",
        action="change_address",
        target_type="order",
        target_id=order_id,
        tool_name="order_tool.change_address",
        tool_args={"order_id": order_id, "new_address": "DEMO_MASKED_ADDRESS"},
        reason="demo pending action for address change",
    )
    now = datetime.now(UTC)
    return {
        "pending_action_id": pending_action_id,
        "session_id": session_id,
        "source_run_id": run_id,
        "user_id": user_id,
        "action_plan_json": json.dumps(plan.to_dict(), ensure_ascii=False),
        "risk_level": "L2",
        "status": status,
        "expires_at": expires_at.isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


def _checkpoint_rows(now: datetime) -> list[dict[str, Any]]:
    pending_rows = _pending_action_rows(now)
    rows = []
    for pending in pending_rows:
        suffix = pending["pending_action_id"].replace("pa_demo_", "")
        rows.append(
            {
                "checkpoint_id": f"cp_demo_{suffix}",
                "run_id": pending["source_run_id"],
                "session_id": pending["session_id"],
                "user_id": pending["user_id"],
                "current_node": "pending_action_node",
                "checkpoint_type": "WAITING_CONFIRMATION",
                "state_snapshot_json": json.dumps(
                    {
                        "pending_action_id": pending["pending_action_id"],
                        "action_plan": json.loads(pending["action_plan_json"]),
                        "risk_level": pending["risk_level"],
                    },
                    ensure_ascii=False,
                ),
                "resume_policy_json": json.dumps(
                    {
                        "resume_api": "/api/checkpoints/{checkpoint_id}/resume",
                        "next_api": "/api/confirm",
                        "requires_validator": True,
                        "requires_policy": True,
                        "tool_execution_on_resume": False,
                    },
                    ensure_ascii=False,
                ),
                "status": (
                    "WAITING_CONFIRMATION"
                    if pending["status"] == "PENDING"
                    else pending["status"]
                ),
                "expires_at": pending["expires_at"],
                "created_at": pending["created_at"],
                "updated_at": pending["updated_at"],
            }
        )
    return rows


def _pending_values(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["pending_action_id"],
        row["session_id"],
        row["source_run_id"],
        row["user_id"],
        row["action_plan_json"],
        row["risk_level"],
        row["status"],
        row["expires_at"],
        row["created_at"],
        row["updated_at"],
    )


def _pending_event_values(row: dict[str, Any], now: datetime) -> tuple[Any, ...]:
    return (
        f"evt_{row['pending_action_id']}_seed",
        row["pending_action_id"],
        row["source_run_id"],
        None,
        row["session_id"],
        row["user_id"],
        None,
        "CREATED",
        None,
        row["status"],
        "demo seed",
        "{}",
        now.isoformat(),
    )


def _checkpoint_values(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["checkpoint_id"],
        row["run_id"],
        None,
        row["session_id"],
        row["user_id"],
        row["current_node"],
        row["checkpoint_type"],
        row["state_snapshot_json"],
        row["resume_policy_json"],
        row["status"],
        row["expires_at"],
        row["created_at"],
        row["updated_at"],
    )


def _checkpoint_event_values(row: dict[str, Any], now: datetime) -> tuple[Any, ...]:
    return (
        f"evt_{row['checkpoint_id']}_seed",
        row["checkpoint_id"],
        row["run_id"],
        None,
        row["session_id"],
        row["user_id"],
        "CREATED",
        None,
        row["status"],
        "demo seed",
        "{}",
        now.isoformat(),
    )


def _count_demo_rows(connection) -> dict[str, int]:
    demo_ids = _demo_id_sets()
    counts = {}
    with connection.cursor() as cursor:
        for key, table, column in [
            ("users", "users", "id"),
            ("orders", "orders", "id"),
            ("tickets", "tickets", "id"),
            ("pending_actions", "pending_actions", "pending_action_id"),
            ("checkpoints", "checkpoints", "checkpoint_id"),
        ]:
            cursor.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {column} = ANY(%s)",
                (demo_ids[key],),
            )
            counts[key] = int(cursor.fetchone()[0])
    counts["note"] = "missing user/order scenarios are represented by queries for absent IDs"
    return counts


def _demo_id_sets() -> dict[str, list[str]]:
    return {
        "users": [row["id"] for row in SEED_USERS],
        "orders": [row["id"] for row in SEED_ORDERS],
        "tickets": [row["id"] for row in DEMO_TICKETS],
        "pending_actions": [
            "pa_demo_waiting_confirm",
            "pa_demo_cancelled",
            "pa_demo_expired",
            "pa_demo_resumable",
        ],
        "checkpoints": [
            "cp_demo_waiting_confirm",
            "cp_demo_cancelled",
            "cp_demo_expired",
            "cp_demo_resumable",
        ],
        "runs": [
            "run_demo_waiting_confirm",
            "run_demo_cancelled",
            "run_demo_expired",
            "run_demo_resumable",
            "run_demo_ticket_open",
            "run_demo_ticket_processing",
            "run_demo_ticket_closed",
        ],
    }


def _connect(database_url: str):
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required for PostgreSQL demo seed") from exc
    return psycopg.connect(database_url, connect_timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
