import json

import pytest

from app.core.action_plan_validator import ActionPlanValidator
from app.core.llm_models import SCHEMA_VERSION
from app.llm import (
    LLMContractError,
    candidate_to_action_plan,
    parse_action_plan_candidate,
    parse_intent_result,
)


def test_parse_intent_result_accepts_valid_schema() -> None:
    result = parse_intent_result(
        _json(
            {
                "schema_version": SCHEMA_VERSION,
                "intent": "order_query",
                "confidence": 0.9,
                "entities": {"order_id": "O10086"},
            }
        )
    )

    assert result.intent == "order_query"
    assert result.confidence == 0.9
    assert result.entities == {"order_id": "O10086"}


def test_parse_intent_result_rejects_unknown_schema_version() -> None:
    with pytest.raises(LLMContractError):
        parse_intent_result(
            _json(
                {
                    "schema_version": "2.0",
                    "intent": "order_query",
                    "confidence": 0.9,
                    "entities": {},
                }
            )
        )


def test_parse_intent_result_rejects_missing_intent() -> None:
    with pytest.raises(LLMContractError):
        parse_intent_result(
            _json(
                {
                    "schema_version": SCHEMA_VERSION,
                    "confidence": 0.9,
                    "entities": {},
                }
            )
        )


def test_parse_action_plan_candidate_accepts_valid_schema() -> None:
    candidate = parse_action_plan_candidate(_valid_action_plan_json())

    assert candidate.action == "query_order"
    assert candidate.tool_name == "order_tool.query_order"
    assert candidate.tool_args == {"order_id": "O10086"}


def test_parse_action_plan_candidate_rejects_non_object_tool_args() -> None:
    payload = _valid_action_plan_payload()
    payload["tool_args"] = "not object"

    with pytest.raises(LLMContractError):
        parse_action_plan_candidate(_json(payload))


def test_parse_action_plan_candidate_rejects_non_string_tool_name() -> None:
    payload = _valid_action_plan_payload()
    payload["tool_name"] = 123

    with pytest.raises(LLMContractError):
        parse_action_plan_candidate(_json(payload))


def test_candidate_to_action_plan_still_goes_through_validator() -> None:
    candidate = parse_action_plan_candidate(_valid_action_plan_json())
    action_plan = candidate_to_action_plan(candidate)

    validation_result = ActionPlanValidator().validate(action_plan)

    assert validation_result.is_valid is True


def _valid_action_plan_json() -> str:
    return _json(_valid_action_plan_payload())


def _valid_action_plan_payload() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "intent": "order_query",
        "action": "query_order",
        "target_type": "order",
        "target_id": "O10086",
        "tool_name": "order_tool.query_order",
        "tool_args": {"order_id": "O10086"},
        "reason": "用户查询订单",
        "confidence": 0.91,
    }


def _json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False)
