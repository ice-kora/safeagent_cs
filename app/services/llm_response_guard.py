import re

from app.core.llm_models import GuardStatus, LLMGuardResult, LLMResponseDraft


class LLMResponseGuard:
    """校验 LLM 生成后的用户回复草稿。

    该 Guard 只检查回复文本是否违背系统状态、策略裁决或敏感信息边界。
    它不调用 LLM，不判断权限，不调用工具，也不修改任何业务状态。
    """

    FIXED_SAFE_RESPONSE = "当前请求已进入安全处理流程，请以系统状态提示为准。"

    SUCCESS_CLAIM_KEYWORDS = (
        "已处理",
        "已完成",
        "已经为你",
        "操作成功",
        "成功处理",
        "处理完成",
        "修改成功",
    )
    CONFIRM_EXECUTED_KEYWORDS = (
        "已经修改",
        "已执行",
        "修改成功",
        "已为你修改",
    )
    HUMAN_AUTO_HANDLED_KEYWORDS = (
        "已自动退款",
        "已自动处理",
        "已经自动为你",
    )
    SENSITIVE_KEYWORDS = (
        "api key",
        "api_key",
        "token",
        "系统 prompt",
        "system prompt",
        "traceback",
        "stack trace",
        "详细地址",
        "身份证",
        "银行卡",
    )
    PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")

    def guard_response(
        self,
        draft: LLMResponseDraft,
        expected_status: str,
        expected_policy_decision: str | None,
        tool_result_success: bool | None,
        rule_based_response: str | None = None,
    ) -> LLMGuardResult:
        """检查回复草稿，并在不安全时返回 fallback 回复。"""
        blocked_reason = self._get_blocked_reason(
            draft=draft,
            expected_status=expected_status,
            expected_policy_decision=expected_policy_decision,
            tool_result_success=tool_result_success,
        )
        if blocked_reason:
            return self._blocked(blocked_reason, rule_based_response)

        return LLMGuardResult(
            guard_status=GuardStatus.VALID.value,
            sanitized_payload={"response_text": draft.response_text},
            fallback_required=False,
            blocked_reason=None,
            confidence=None,
        )

    def _get_blocked_reason(
        self,
        draft: LLMResponseDraft,
        expected_status: str,
        expected_policy_decision: str | None,
        tool_result_success: bool | None,
    ) -> str | None:
        text = draft.response_text

        if draft.referenced_status != expected_status:
            return "referenced_status 与系统状态不一致"
        if (
            expected_policy_decision is not None
            and draft.referenced_policy_decision != expected_policy_decision
        ):
            return "referenced_policy_decision 与策略裁决不一致"
        if (
            tool_result_success is not None
            and draft.referenced_tool_result_success != tool_result_success
        ):
            return "referenced_tool_result_success 与工具结果不一致"

        if expected_status == "DENY" and self._contains_any(
            text,
            self.SUCCESS_CLAIM_KEYWORDS,
        ):
            return "DENY 回复被改写成成功"
        if expected_status == "CONFIRM_REQUIRED" and self._contains_any(
            text,
            self.CONFIRM_EXECUTED_KEYWORDS,
        ):
            return "CONFIRM_REQUIRED 回复被改写成已执行"
        if expected_status == "HUMAN_REQUIRED" and self._contains_any(
            text,
            self.HUMAN_AUTO_HANDLED_KEYWORDS,
        ):
            return "HUMAN_REQUIRED 回复被改写成自动处理"
        if tool_result_success is not True and self._contains_any(
            text,
            self.SUCCESS_CLAIM_KEYWORDS,
        ):
            return "工具未成功但回复声称成功"
        if self._contains_sensitive_pattern(text):
            return "回复包含敏感信息模式"
        return None

    def _blocked(
        self,
        blocked_reason: str,
        rule_based_response: str | None,
    ) -> LLMGuardResult:
        safe_response = rule_based_response or self.FIXED_SAFE_RESPONSE
        return LLMGuardResult(
            guard_status=GuardStatus.BLOCKED.value,
            sanitized_payload={"response_text": safe_response},
            fallback_required=True,
            blocked_reason=blocked_reason,
            confidence=None,
        )

    @staticmethod
    def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _contains_sensitive_pattern(self, text: str) -> bool:
        normalized = text.lower()
        if self.PHONE_PATTERN.search(text):
            return True
        return any(keyword in normalized for keyword in self.SENSITIVE_KEYWORDS)
