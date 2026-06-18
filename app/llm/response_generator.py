from dataclasses import dataclass, field

from app.core.llm_models import LLMResponseDraft
from app.llm.provider import BaseLLMProvider, LLMRequest


@dataclass
class LLMResponseGenerator:
    """LLM 回复草稿生成器。

    Generator 只能接收安全摘要并生成草稿。它不决定业务状态，不修改
    PolicyDecision，也不能声明未执行的工具已经成功。
    """

    provider: BaseLLMProvider
    fallback_response: str = "当前请求已进入安全处理流程，请以系统状态提示为准。"
    metadata: dict[str, str] = field(default_factory=dict)

    def generate(
        self,
        *,
        status: str,
        policy_decision: str | None,
        tool_result_success: bool | None,
        safe_summary: str,
        public_reason: str | None = None,
    ) -> LLMResponseDraft:
        """基于安全摘要生成 LLMResponseDraft。"""
        try:
            response = self.provider.complete(
                LLMRequest(
                    system_prompt=(
                        "你是 SafeAgent-CS 的回复润色器。只能基于安全摘要表达，"
                        "不能改变系统状态，不能编造工具执行结果。"
                    ),
                    user_prompt=self._build_safe_prompt(
                        status=status,
                        policy_decision=policy_decision,
                        tool_result_success=tool_result_success,
                        safe_summary=safe_summary,
                        public_reason=public_reason,
                    ),
                    task_type="response",
                    temperature=0.2,
                    metadata={"adapter": "LLMResponseGenerator", **self.metadata},
                )
            )
            response_text = response.text.strip() or self.fallback_response
        except Exception:
            response_text = self.fallback_response

        return LLMResponseDraft(
            response_text=response_text,
            referenced_status=status,
            referenced_policy_decision=policy_decision,
            referenced_tool_result_success=tool_result_success,
            safe_for_user_candidate=True,
        )

    @staticmethod
    def _build_safe_prompt(
        *,
        status: str,
        policy_decision: str | None,
        tool_result_success: bool | None,
        safe_summary: str,
        public_reason: str | None,
    ) -> str:
        return "\n".join(
            [
                f"status: {status}",
                f"policy_decision: {policy_decision}",
                f"tool_result_success: {tool_result_success}",
                f"safe_summary: {safe_summary}",
                f"public_reason: {public_reason or ''}",
            ]
        )
