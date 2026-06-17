from app.core.llm_models import (
    SCHEMA_VERSION,
    FallbackReasonCode,
    GuardStatus,
    LLMActionPlanCandidate,
    LLMGuardResult,
    LLMIntentResult,
    LLMResponseDraft,
    Mode,
    ModeDecision,
)


def test_schema_version_is_1_0() -> None:
    assert SCHEMA_VERSION == "1.0"


def test_llm_intent_result_can_be_created() -> None:
    result = LLMIntentResult(
        intent="order_query",
        confidence=0.92,
        entities={"order_id": "O10086"},
        raw_user_message_hash="hash_001",
    )

    assert result.schema_version == SCHEMA_VERSION
    assert result.intent == "order_query"
    assert result.confidence == 0.92
    assert result.entities["order_id"] == "O10086"


def test_llm_action_plan_candidate_can_be_created() -> None:
    candidate = LLMActionPlanCandidate(
        intent="order_query",
        action="query_order",
        target_type="order",
        target_id="O10086",
        tool_name="order_tool.query_order",
        tool_args={"order_id": "O10086"},
        reason="用户想查询订单状态",
        confidence=0.91,
    )

    assert candidate.schema_version == SCHEMA_VERSION
    assert candidate.action == "query_order"
    assert candidate.target_id == "O10086"
    assert candidate.tool_args["order_id"] == "O10086"


def test_llm_response_draft_can_be_created() -> None:
    draft = LLMResponseDraft(
        response_text="订单查询完成。",
        referenced_status="SUCCESS",
        referenced_policy_decision="ALLOW",
        referenced_tool_result_success=True,
        safe_for_user_candidate=True,
    )

    assert draft.schema_version == SCHEMA_VERSION
    assert draft.response_text == "订单查询完成。"
    assert draft.referenced_tool_result_success is True
    assert draft.safe_for_user_candidate is True


def test_llm_guard_result_can_be_created() -> None:
    result = LLMGuardResult(
        guard_status=GuardStatus.VALID.value,
        sanitized_payload={"intent": "policy_query"},
        fallback_required=False,
        blocked_reason=None,
        confidence=0.86,
    )

    assert result.schema_version == SCHEMA_VERSION
    assert result.guard_status == GuardStatus.VALID.value
    assert result.sanitized_payload == {"intent": "policy_query"}
    assert result.fallback_required is False


def test_mode_decision_can_be_created() -> None:
    decision = ModeDecision(
        requested_mode=Mode.HYBRID.value,
        effective_mode=Mode.RULE.value,
        intent_source="rule",
        planner_source="rule",
        fallback_required=True,
        fallback_reason_code=FallbackReasonCode.NO_API_KEY.value,
        fallback_reason="LLM API key 未配置",
        llm_enabled=False,
    )

    assert decision.schema_version == SCHEMA_VERSION
    assert decision.requested_mode == "hybrid"
    assert decision.effective_mode == "rule"
    assert decision.fallback_reason_code == "NO_API_KEY"
    assert decision.llm_enabled is False


def test_guard_status_constants_exist() -> None:
    assert GuardStatus.VALID.value == "VALID"
    assert GuardStatus.INVALID_JSON.value == "INVALID_JSON"
    assert GuardStatus.SCHEMA_INVALID.value == "SCHEMA_INVALID"
    assert GuardStatus.LOW_CONFIDENCE.value == "LOW_CONFIDENCE"
    assert GuardStatus.FORBIDDEN_OUTPUT.value == "FORBIDDEN_OUTPUT"
    assert GuardStatus.BLOCKED.value == "BLOCKED"


def test_mode_constants_exist() -> None:
    assert Mode.RULE.value == "rule"
    assert Mode.HYBRID.value == "hybrid"
    assert Mode.LLM.value == "llm"
    assert Mode.LLM_STRICT.value == "llm_strict"


def test_fallback_reason_code_constants_exist() -> None:
    assert FallbackReasonCode.NO_API_KEY.value == "NO_API_KEY"
    assert FallbackReasonCode.LLM_TIMEOUT.value == "LLM_TIMEOUT"
    assert FallbackReasonCode.LLM_PROVIDER_ERROR.value == "LLM_PROVIDER_ERROR"
    assert FallbackReasonCode.INVALID_JSON.value == "INVALID_JSON"
    assert FallbackReasonCode.SCHEMA_INVALID.value == "SCHEMA_INVALID"
    assert FallbackReasonCode.LOW_CONFIDENCE.value == "LOW_CONFIDENCE"
    assert FallbackReasonCode.FORBIDDEN_OUTPUT.value == "FORBIDDEN_OUTPUT"
    assert (
        FallbackReasonCode.RESPONSE_GUARD_BLOCKED.value
        == "RESPONSE_GUARD_BLOCKED"
    )
    assert FallbackReasonCode.LLM_STRICT_DISABLED.value == "LLM_STRICT_DISABLED"
    assert FallbackReasonCode.UNKNOWN.value == "UNKNOWN"
