from app.llm import LLMRequest, LLMResponse, LLMResponseGenerator, MockLLMProvider


class CapturingProvider:
    name = "capturing"

    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(text=self.text, provider_name=self.name)


class RaisingProvider:
    name = "raising"

    def complete(self, request: LLMRequest) -> LLMResponse:
        raise RuntimeError("provider failed")


def test_response_generator_returns_response_draft() -> None:
    generator = LLMResponseGenerator(
        provider=MockLLMProvider(response_map={"response": "订单查询完成。"})
    )

    draft = generator.generate(
        status="SUCCESS",
        policy_decision="ALLOW",
        tool_result_success=True,
        safe_summary="订单状态为已支付，物流待发货。",
    )

    assert draft.response_text == "订单查询完成。"
    assert draft.referenced_status == "SUCCESS"
    assert draft.referenced_policy_decision == "ALLOW"
    assert draft.referenced_tool_result_success is True


def test_response_generator_only_sends_safe_summary_to_provider() -> None:
    provider = CapturingProvider(text="安全回复。")
    generator = LLMResponseGenerator(provider=provider)

    generator.generate(
        status="DENY",
        policy_decision="DENY",
        tool_result_success=None,
        safe_summary="策略拒绝。",
        public_reason="订单不属于当前用户。",
    )

    request = provider.requests[0]
    assert "策略拒绝" in request.user_prompt
    assert "订单不属于当前用户" in request.user_prompt
    assert "13812345678" not in request.user_prompt
    assert "详细地址" not in request.user_prompt
    assert "api_key" not in request.user_prompt


def test_response_generator_falls_back_when_provider_fails() -> None:
    generator = LLMResponseGenerator(
        provider=RaisingProvider(),
        fallback_response="规则安全回复。",
    )

    draft = generator.generate(
        status="TOOL_FAILED",
        policy_decision="ALLOW",
        tool_result_success=False,
        safe_summary="工具调用失败。",
    )

    assert draft.response_text == "规则安全回复。"
    assert draft.referenced_status == "TOOL_FAILED"


def test_response_generator_does_not_change_business_status() -> None:
    generator = LLMResponseGenerator(
        provider=MockLLMProvider(response_map={"response": "已经为你成功处理。"})
    )

    draft = generator.generate(
        status="DENY",
        policy_decision="DENY",
        tool_result_success=None,
        safe_summary="策略拒绝。",
    )

    assert draft.response_text == "已经为你成功处理。"
    assert draft.referenced_status == "DENY"
    assert draft.referenced_policy_decision == "DENY"
