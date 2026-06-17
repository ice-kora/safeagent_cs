import json

from app.workflows.checkpoint_policy import (
    CHECKPOINT_MATRIX_NODES,
    CheckpointNodeRisk,
    build_checkpoint_resume_matrix,
)


def test_checkpoint_resume_matrix_contains_required_nodes() -> None:
    matrix = build_checkpoint_resume_matrix()
    node_names = {entry.node_name for entry in matrix}

    assert set(CHECKPOINT_MATRIX_NODES).issubset(node_names)


def test_side_effect_nodes_disable_real_resume() -> None:
    matrix = _matrix_by_node()

    for node_name in (
        "tool_gateway_node",
        "pending_action_node",
        "failure_handler_node",
    ):
        entry = matrix[node_name]
        assert entry.risk == CheckpointNodeRisk.SIDE_EFFECT
        assert entry.checkpoint_allowed is True
        assert entry.dry_run_allowed is True
        assert entry.real_resume_allowed_now is False


def test_safe_nodes_allow_checkpoint_and_dry_run_but_not_real_resume() -> None:
    matrix = _matrix_by_node()

    for node_name in (
        "intent_node",
        "planner_node",
        "policy_node",
        "route_by_policy_node",
        "response_generation_node",
    ):
        entry = matrix[node_name]
        assert entry.risk == CheckpointNodeRisk.SAFE
        assert entry.checkpoint_allowed is True
        assert entry.dry_run_allowed is True
        assert entry.real_resume_allowed_now is False


def test_terminal_node_allows_checkpoint_and_dry_run_only() -> None:
    entry = _matrix_by_node()["finish_node"]

    assert entry.risk == CheckpointNodeRisk.TERMINAL
    assert entry.checkpoint_allowed is True
    assert entry.dry_run_allowed is True
    assert entry.real_resume_allowed_now is False


def test_unknown_node_is_fully_rejected() -> None:
    entry = _matrix_by_node()["unknown_node"]

    assert entry.risk == CheckpointNodeRisk.UNSAFE_TO_RESUME
    assert entry.checkpoint_allowed is False
    assert entry.dry_run_allowed is False
    assert entry.real_resume_allowed_now is False


def test_checkpoint_resume_matrix_is_json_safe() -> None:
    payload = [entry.to_dict() for entry in build_checkpoint_resume_matrix()]

    serialized = json.dumps(payload, ensure_ascii=False)
    loaded = json.loads(serialized)

    assert loaded[0]["node_name"]
    assert all(isinstance(entry["risk"], str) for entry in loaded)


def _matrix_by_node():
    return {entry.node_name: entry for entry in build_checkpoint_resume_matrix()}
