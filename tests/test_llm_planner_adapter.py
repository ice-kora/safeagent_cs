import inspect

from app.core.action_plan import ActionPlan
from app.llm import LLMActionPlanner, LLMRequest, LLMResponse, MockLLMProvider
from app.llm import planner_adapter


class RaisingProvider:
    name = "raising"

    def complete(self, request: LLMRequest) -> LLMResponse:
        raise RuntimeError("provider failed")


def test_valid_json_generates_action_plan() -> None:
    planner = LLMActionPlanner(
        provider=MockLLMProvider(
            response_map={
                "planner": """
                {
                  "intent": "order_query",
                  "action": "query_order",
                  "target_type": "order",
                  "target_id": "O10086",
                  "tool_name": "order_tool.query_order",
                  "tool_args": {"order_id": "O10086"},
                  "reason": "用户想查询订单"
                }
                """
            }
        )
    )

    plan = planner.plan(intent="order_query", message="帮我查一下订单 O10086")

    assert plan == ActionPlan(
        intent="order_query",
        action="query_order",
        target_type="order",
        target_id="O10086",
        tool_name="order_tool.query_order",
        tool_args={"order_id": "O10086"},
        reason="用户想查询订单",
    )


def test_invalid_json_falls_back_to_rule_based_planner() -> None:
    planner = LLMActionPlanner(
        provider=MockLLMProvider(response_map={"planner": "not json"})
    )

    plan = planner.plan(intent="order_query", message="帮我查一下订单 O10086")

    assert plan.action == "query_order"
    assert plan.target_id == "O10086"


def test_missing_action_falls_back_to_rule_based_planner() -> None:
    planner = LLMActionPlanner(
        provider=MockLLMProvider(
            response_map={
                "planner": '{"intent": "order_query", "target_type": "order"}'
            }
        )
    )

    plan = planner.plan(intent="refund_request", message="我要把订单 O10086 退款")

    assert plan.action == "request_refund"
    assert plan.target_id == "O10086"


def test_missing_target_type_falls_back_to_rule_based_planner() -> None:
    planner = LLMActionPlanner(
        provider=MockLLMProvider(
            response_map={"planner": '{"intent": "order_query", "action": "query_order"}'}
        )
    )

    plan = planner.plan(intent="address_change", message="订单 O10086 的地址填错了")

    assert plan.action == "change_address"
    assert plan.target_id == "O10086"


def test_non_object_tool_args_falls_back_to_rule_based_planner() -> None:
    planner = LLMActionPlanner(
        provider=MockLLMProvider(
            response_map={
                "planner": """
                {
                  "intent": "order_query",
                  "action": "query_order",
                  "target_type": "order",
                  "tool_args": "not object"
                }
                """
            }
        )
    )

    plan = planner.plan(intent="complaint", message="我要投诉客服")

    assert plan.action == "create_complaint_ticket"


def test_provider_exception_falls_back_to_rule_based_planner() -> None:
    planner = LLMActionPlanner(provider=RaisingProvider())

    plan = planner.plan(intent="policy_query", message="你们支持七天无理由退货吗？")

    assert plan.action == "query_policy"
    assert plan.tool_name == "knowledge_tool.query_policy"


def test_generated_result_does_not_call_tool_gateway() -> None:
    source = inspect.getsource(planner_adapter)

    assert "ToolGateway" not in source
    assert "call_tool" not in source
    assert "order_tool" not in source
    assert "ticket_tool" not in source
    assert "knowledge_tool" not in source


def test_llm_planner_only_returns_candidate_action_plan() -> None:
    planner = LLMActionPlanner(
        provider=MockLLMProvider(
            response_map={
                "planner": """
                {
                  "intent": "order_query",
                  "action": "query_order",
                  "target_type": "order",
                  "target_id": "O10086",
                  "tool_name": "order_tool.query_order",
                  "tool_args": {"order_id": "O10086"}
                }
                """
            }
        )
    )

    plan = planner.plan(intent="order_query", message="帮我查一下订单 O10086")

    assert isinstance(plan, ActionPlan)
    assert plan.tool_name == "order_tool.query_order"
