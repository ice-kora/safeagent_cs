import pytest

from app.storage.runtime_config import RuntimePostgresConfigurationError
from app.storage.runtime_postgres import (
    RUNTIME_POSTGRES_SCHEMA_SQL,
    PostgresRuntimeStore,
)


def test_runtime_postgres_schema_contains_runtime_tables() -> None:
    schema = RUNTIME_POSTGRES_SCHEMA_SQL

    for table_name in (
        "agent_runs",
        "agent_traces",
        "policy_logs",
        "tool_call_logs",
        "pending_action_events",
        "failure_logs",
        "security_logs",
        "pending_actions",
        "tickets",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in schema


def test_runtime_postgres_store_requires_database_url() -> None:
    with pytest.raises(RuntimePostgresConfigurationError):
        PostgresRuntimeStore(database_url=None)
