from app.core.action_plan import ActionPlan
from app.core.constants import PolicyDecisionType
from app.core.ids import (
    generate_pending_action_id,
    generate_request_id,
    generate_run_id,
    generate_ticket_id,
    generate_trace_node_id,
)
from app.core.policy import PolicyDecision
from app.core.risk import RiskLevel


def test_id_prefixes_are_clear() -> None:
    assert generate_request_id().startswith("req_")
    assert generate_run_id().startswith("run_")
    assert generate_trace_node_id().startswith("tn_")
    assert generate_pending_action_id().startswith("pa_")
    assert generate_ticket_id().startswith("tk_")


def test_core_data_structures_are_usable() -> None:
    plan = ActionPlan(
        intent="order_query",
        action="query_order",
        target_type="order",
        target_id="O10086",
        tool_name="order_tool.query_order",
        tool_args={"order_id": "O10086"},
        reason="user asks order status",
    )
    decision = PolicyDecision(
        decision=PolicyDecisionType.ALLOW,
        risk_level=RiskLevel.L2,
        reason="own order",
    )

    assert plan.to_dict()["tool_args"]["order_id"] == "O10086"
    assert decision.to_dict() == {
        "decision": "ALLOW",
        "risk_level": "L2",
        "reason": "own order",
    }
