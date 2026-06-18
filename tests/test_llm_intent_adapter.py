import socket

from app.llm import LLMIntentClassifier, LLMRequest, LLMResponse, MockLLMProvider


class RaisingProvider:
    name = "raising"

    def complete(self, request: LLMRequest) -> LLMResponse:
        raise RuntimeError("provider failed")


def test_valid_json_returns_intent() -> None:
    classifier = LLMIntentClassifier(
        provider=MockLLMProvider(response_map={"intent": '{"intent": "order_query"}'})
    )

    intent = classifier.classify("随便一句话")

    assert intent == "order_query"


def test_invalid_json_falls_back_to_rule_based_classifier() -> None:
    classifier = LLMIntentClassifier(
        provider=MockLLMProvider(response_map={"intent": "not json"})
    )

    intent = classifier.classify("我要投诉客服")

    assert intent == "complaint"


def test_missing_intent_falls_back_to_rule_based_classifier() -> None:
    classifier = LLMIntentClassifier(
        provider=MockLLMProvider(response_map={"intent": '{"confidence": 0.9}'})
    )

    intent = classifier.classify("我要退款")

    assert intent == "refund_request"


def test_non_string_intent_falls_back_to_rule_based_classifier() -> None:
    classifier = LLMIntentClassifier(
        provider=MockLLMProvider(response_map={"intent": '{"intent": 123}'})
    )

    intent = classifier.classify("你们支持七天无理由退货吗？")

    assert intent == "policy_query"


def test_provider_exception_falls_back_to_rule_based_classifier() -> None:
    classifier = LLMIntentClassifier(provider=RaisingProvider())

    intent = classifier.classify("帮我查一下订单 O10086")

    assert intent == "order_query"


def test_llm_intent_classifier_does_not_access_external_network(monkeypatch) -> None:
    def fail_connect(*args, **kwargs):
        raise AssertionError("LLMIntentClassifier test path must not access network")

    monkeypatch.setattr(socket.socket, "connect", fail_connect)
    classifier = LLMIntentClassifier(
        provider=MockLLMProvider(response_map={"intent": '{"intent": "unknown"}'})
    )

    assert classifier.classify("普通文本") == "unknown"
