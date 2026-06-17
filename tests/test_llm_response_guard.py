from app.core.llm_models import GuardStatus, LLMResponseDraft
from app.services.llm_response_guard import LLMResponseGuard


def _draft(
    response_text: str,
    referenced_status: str = "SUCCESS",
    referenced_policy_decision: str | None = "ALLOW",
    referenced_tool_result_success: bool | None = True,
) -> LLMResponseDraft:
    return LLMResponseDraft(
        response_text=response_text,
        referenced_status=referenced_status,
        referenced_policy_decision=referenced_policy_decision,
        referenced_tool_result_success=referenced_tool_result_success,
        safe_for_user_candidate=True,
    )


def test_normal_deny_response_passes() -> None:
    result = LLMResponseGuard().guard_response(
        draft=_draft(
            response_text="该请求无法处理。",
            referenced_status="DENY",
            referenced_policy_decision="DENY",
            referenced_tool_result_success=None,
        ),
        expected_status="DENY",
        expected_policy_decision="DENY",
        tool_result_success=None,
    )

    assert result.guard_status == GuardStatus.VALID.value
    assert result.fallback_required is False
    assert result.sanitized_payload["response_text"] == "该请求无法处理。"


def test_deny_rewritten_as_success_is_blocked() -> None:
    result = LLMResponseGuard().guard_response(
        draft=_draft(
            response_text="已经为你成功处理。",
            referenced_status="DENY",
            referenced_policy_decision="DENY",
            referenced_tool_result_success=None,
        ),
        expected_status="DENY",
        expected_policy_decision="DENY",
        tool_result_success=None,
    )

    assert result.guard_status == GuardStatus.BLOCKED.value
    assert result.fallback_required is True


def test_confirm_required_rewritten_as_executed_is_blocked() -> None:
    result = LLMResponseGuard().guard_response(
        draft=_draft(
            response_text="地址已经修改。",
            referenced_status="CONFIRM_REQUIRED",
            referenced_policy_decision="CONFIRM_REQUIRED",
            referenced_tool_result_success=None,
        ),
        expected_status="CONFIRM_REQUIRED",
        expected_policy_decision="CONFIRM_REQUIRED",
        tool_result_success=None,
    )

    assert result.guard_status == GuardStatus.BLOCKED.value
    assert result.fallback_required is True


def test_human_required_rewritten_as_auto_handled_is_blocked() -> None:
    result = LLMResponseGuard().guard_response(
        draft=_draft(
            response_text="已自动退款。",
            referenced_status="HUMAN_REQUIRED",
            referenced_policy_decision="HUMAN_REQUIRED",
            referenced_tool_result_success=None,
        ),
        expected_status="HUMAN_REQUIRED",
        expected_policy_decision="HUMAN_REQUIRED",
        tool_result_success=None,
    )

    assert result.guard_status == GuardStatus.BLOCKED.value
    assert result.fallback_required is True


def test_failed_tool_rewritten_as_success_is_blocked() -> None:
    result = LLMResponseGuard().guard_response(
        draft=_draft(
            response_text="操作成功。",
            referenced_status="TOOL_FAILED",
            referenced_policy_decision="ALLOW",
            referenced_tool_result_success=False,
        ),
        expected_status="TOOL_FAILED",
        expected_policy_decision="ALLOW",
        tool_result_success=False,
    )

    assert result.guard_status == GuardStatus.BLOCKED.value
    assert result.fallback_required is True


def test_phone_number_is_blocked() -> None:
    result = LLMResponseGuard().guard_response(
        draft=_draft(response_text="手机号是 13812345678。"),
        expected_status="SUCCESS",
        expected_policy_decision="ALLOW",
        tool_result_success=True,
    )

    assert result.guard_status == GuardStatus.BLOCKED.value


def test_api_key_or_token_is_blocked() -> None:
    result = LLMResponseGuard().guard_response(
        draft=_draft(response_text="token 是 secret-token。"),
        expected_status="SUCCESS",
        expected_policy_decision="ALLOW",
        tool_result_success=True,
    )

    assert result.guard_status == GuardStatus.BLOCKED.value


def test_referenced_status_mismatch_is_blocked() -> None:
    result = LLMResponseGuard().guard_response(
        draft=_draft(response_text="请求已进入处理。", referenced_status="SUCCESS"),
        expected_status="DENY",
        expected_policy_decision="ALLOW",
        tool_result_success=True,
    )

    assert result.guard_status == GuardStatus.BLOCKED.value
    assert "referenced_status" in result.blocked_reason


def test_referenced_policy_decision_mismatch_is_blocked() -> None:
    result = LLMResponseGuard().guard_response(
        draft=_draft(
            response_text="请求已进入处理。",
            referenced_policy_decision="ALLOW",
        ),
        expected_status="SUCCESS",
        expected_policy_decision="DENY",
        tool_result_success=True,
    )

    assert result.guard_status == GuardStatus.BLOCKED.value
    assert "referenced_policy_decision" in result.blocked_reason


def test_referenced_tool_result_success_mismatch_is_blocked() -> None:
    result = LLMResponseGuard().guard_response(
        draft=_draft(
            response_text="请求已进入处理。",
            referenced_tool_result_success=True,
        ),
        expected_status="SUCCESS",
        expected_policy_decision="ALLOW",
        tool_result_success=False,
    )

    assert result.guard_status == GuardStatus.BLOCKED.value
    assert "referenced_tool_result_success" in result.blocked_reason


def test_blocked_prefers_rule_based_response() -> None:
    result = LLMResponseGuard().guard_response(
        draft=_draft(
            response_text="已经为你成功处理。",
            referenced_status="DENY",
            referenced_policy_decision="DENY",
            referenced_tool_result_success=None,
        ),
        expected_status="DENY",
        expected_policy_decision="DENY",
        tool_result_success=None,
        rule_based_response="该请求已被拒绝。",
    )

    assert result.guard_status == GuardStatus.BLOCKED.value
    assert result.sanitized_payload["response_text"] == "该请求已被拒绝。"


def test_blocked_uses_fixed_safe_response_without_rule_based_response() -> None:
    result = LLMResponseGuard().guard_response(
        draft=_draft(
            response_text="已经为你成功处理。",
            referenced_status="DENY",
            referenced_policy_decision="DENY",
            referenced_tool_result_success=None,
        ),
        expected_status="DENY",
        expected_policy_decision="DENY",
        tool_result_success=None,
    )

    assert result.guard_status == GuardStatus.BLOCKED.value
    assert (
        result.sanitized_payload["response_text"]
        == LLMResponseGuard.FIXED_SAFE_RESPONSE
    )


def test_fixed_safe_response_does_not_include_original_draft() -> None:
    unsafe_draft = "已经为你成功处理。"

    result = LLMResponseGuard().guard_response(
        draft=_draft(
            response_text=unsafe_draft,
            referenced_status="DENY",
            referenced_policy_decision="DENY",
            referenced_tool_result_success=None,
        ),
        expected_status="DENY",
        expected_policy_decision="DENY",
        tool_result_success=None,
    )

    assert unsafe_draft not in result.sanitized_payload["response_text"]


def test_normal_success_response_passes() -> None:
    result = LLMResponseGuard().guard_response(
        draft=_draft(response_text="订单查询完成。"),
        expected_status="SUCCESS",
        expected_policy_decision="ALLOW",
        tool_result_success=True,
    )

    assert result.guard_status == GuardStatus.VALID.value
    assert result.fallback_required is False
    assert result.sanitized_payload["response_text"] == "订单查询完成。"
