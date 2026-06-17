import json
from copy import deepcopy
from pathlib import Path

from app.storage.db import get_connection
from app.workflows.checkpoint_store import InMemoryCheckpointStore
from app.workflows.langgraph_chat_workflow import run_langgraph_chat_workflow
from app.workflows.langgraph_state_schema import CHECKPOINT_SNAPSHOT_SCHEMA_VERSION
from app.workflows.service_adapters import SafeAgentWorkflowServices


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = PROJECT_ROOT / "app" / "mock_platform"


def test_checkpoint_store_saves_success_state(tmp_path: Path) -> None:
    state, _, _ = _run_state(tmp_path, "帮我查一下订单 O10086")
    store = InMemoryCheckpointStore()

    record = store.save_state_checkpoint(
        state=state,
        node_name="policy_node",
        route="ALLOW",
    )

    assert record.checkpoint_id.startswith("ckpt_")
    assert record.request_id == state.request_id
    assert record.run_id == state.run_id
    assert record.node_name == "policy_node"
    assert record.snapshot["schema_version"] == CHECKPOINT_SNAPSHOT_SCHEMA_VERSION
    assert record.snapshot["final_status"] == "SUCCESS"
    json.dumps(record.snapshot, ensure_ascii=False)


def test_checkpoint_store_get_checkpoint_returns_copy(tmp_path: Path) -> None:
    state, _, _ = _run_state(tmp_path, "帮我查一下订单 O10086")
    store = InMemoryCheckpointStore()
    record = store.save_state_checkpoint(
        state=state,
        node_name="policy_node",
        route="ALLOW",
    )

    fetched = store.get_checkpoint(record.checkpoint_id)
    assert fetched is not None
    fetched.snapshot["final_status"] = "MUTATED"

    fetched_again = store.get_checkpoint(record.checkpoint_id)
    assert fetched_again is not None
    assert fetched_again.snapshot["final_status"] == "SUCCESS"


def test_checkpoint_store_lists_checkpoints_by_run(tmp_path: Path) -> None:
    first_state, _, _ = _run_state(tmp_path, "帮我查一下订单 O10086")
    second_state, _, _ = _run_state(tmp_path, "帮我查一下订单 O10086")
    store = InMemoryCheckpointStore()
    first_record = store.save_state_checkpoint(
        state=first_state,
        node_name="policy_node",
        route="ALLOW",
    )
    store.save_state_checkpoint(
        state=second_state,
        node_name="policy_node",
        route="ALLOW",
    )

    records = store.list_checkpoints_for_run(first_state.run_id)

    assert [record.checkpoint_id for record in records] == [first_record.checkpoint_id]


def test_dry_run_resume_to_policy_node_is_allowed(tmp_path: Path) -> None:
    state, _, _ = _run_state(tmp_path, "帮我查一下订单 O10086")
    store = InMemoryCheckpointStore()
    record = store.save_state_checkpoint(
        state=state,
        node_name="action_plan_validator_node",
        route="ALLOW",
    )

    result = store.dry_run_resume(
        checkpoint_id=record.checkpoint_id,
        next_node="policy_node",
    )

    assert result.decision.allowed is True
    assert result.next_node == "policy_node"
    assert result.snapshot_summary == {
        "request_id": state.request_id,
        "run_id": state.run_id,
        "final_status": "SUCCESS",
        "route": "ALLOW",
        "action": "query_order",
        "policy_decision": "ALLOW",
        "has_tool_result": True,
        "has_pending_action": False,
        "schema_version": CHECKPOINT_SNAPSHOT_SCHEMA_VERSION,
    }


def test_dry_run_resume_to_tool_gateway_node_is_denied_without_side_effect(
    tmp_path: Path,
) -> None:
    state, _, db_path = _run_state(tmp_path, "帮我查一下订单 O10086")
    store = InMemoryCheckpointStore()
    record = store.save_state_checkpoint(
        state=state,
        node_name="policy_node",
        route="ALLOW",
    )
    before_tool_calls = _count_rows(db_path, "tool_call_logs")
    before_pending_actions = _count_rows(db_path, "pending_actions")

    result = store.dry_run_resume(
        checkpoint_id=record.checkpoint_id,
        next_node="tool_gateway_node",
    )

    assert result.decision.allowed is False
    assert "副作用节点" in result.decision.reason
    assert _count_rows(db_path, "tool_call_logs") == before_tool_calls
    assert _count_rows(db_path, "pending_actions") == before_pending_actions


def test_dry_run_resume_to_pending_action_node_is_denied_without_creating_action(
    tmp_path: Path,
) -> None:
    state, _, db_path = _run_state(
        tmp_path,
        "订单 O10086 的地址填错了，帮我改一下",
    )
    store = InMemoryCheckpointStore()
    record = store.save_state_checkpoint(
        state=state,
        node_name="policy_node",
        route="CONFIRM_REQUIRED",
    )
    before_pending_actions = _count_rows(db_path, "pending_actions")
    before_tool_calls = _count_rows(db_path, "tool_call_logs")

    result = store.dry_run_resume(
        checkpoint_id=record.checkpoint_id,
        next_node="pending_action_node",
    )

    assert result.decision.allowed is False
    assert "副作用节点" in result.decision.reason
    assert _count_rows(db_path, "pending_actions") == before_pending_actions == 1
    assert _count_rows(db_path, "tool_call_logs") == before_tool_calls == 0


def test_missing_checkpoint_id_returns_denied_result() -> None:
    store = InMemoryCheckpointStore()

    result = store.dry_run_resume(
        checkpoint_id="ckpt_missing",
        next_node="policy_node",
    )

    assert result.decision.allowed is False
    assert "不存在" in result.decision.reason
    assert result.snapshot_summary == {}


def test_dry_run_resume_does_not_mutate_original_snapshot(tmp_path: Path) -> None:
    state, _, _ = _run_state(tmp_path, "帮我查一下订单 O10086")
    store = InMemoryCheckpointStore()
    record = store.save_state_checkpoint(
        state=state,
        node_name="policy_node",
        route="ALLOW",
    )
    before_snapshot = deepcopy(record.snapshot)

    store.dry_run_resume(
        checkpoint_id=record.checkpoint_id,
        next_node="policy_node",
    )

    after_record = store.get_checkpoint(record.checkpoint_id)
    assert after_record is not None
    assert after_record.snapshot == before_snapshot


def test_snapshot_summary_excludes_full_snapshot_fields(tmp_path: Path) -> None:
    state, _, _ = _run_state(tmp_path, "帮我查一下订单 O10086")
    store = InMemoryCheckpointStore()
    record = store.save_state_checkpoint(
        state=state,
        node_name="policy_node",
        route="ALLOW",
    )

    result = store.dry_run_resume(
        checkpoint_id=record.checkpoint_id,
        next_node="policy_node",
    )

    forbidden_keys = {
        "message",
        "trace_events",
        "errors",
        "action_plan",
        "tool_result",
        "final_response",
    }
    assert forbidden_keys.isdisjoint(result.snapshot_summary.keys())


def _run_state(tmp_path: Path, message: str):
    db_path = tmp_path / "test.db"
    services = SafeAgentWorkflowServices.create_default(
        db_path=db_path,
        mock_dir=MOCK_DIR,
        log_path=tmp_path / "application.log",
    )
    state = run_langgraph_chat_workflow(
        session_id="sess_001",
        user_id="u_1001",
        tenant_id="t_001",
        message=message,
        services=services,
    )
    return state, services, db_path


def _count_rows(db_path: Path, table_name: str) -> int:
    with get_connection(db_path) as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
