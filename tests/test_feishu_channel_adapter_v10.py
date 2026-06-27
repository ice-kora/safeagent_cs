import inspect

from app.channels.feishu_adapter import FeishuChannelAdapter


def test_feishu_challenge_returns_challenge_payload() -> None:
    response = FeishuChannelAdapter().normalize_event({"challenge": "abc"})

    assert response.action == "challenge"
    assert response.payload == {"challenge": "abc"}


def test_feishu_message_event_normalizes_to_chat_message() -> None:
    payload = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"user_id": "ou_1"}},
            "message": {
                "message_id": "om_1",
                "chat_id": "oc_1",
                "message_type": "text",
                "content": "{\"text\":\"帮我查一下订单 O10086\"}",
            },
        },
    }

    response = FeishuChannelAdapter().normalize_event(payload)
    message = response.payload["message"]

    assert response.action == "chat_message"
    assert response.payload["next_api"] == "/api/chat"
    assert message["user_id"] == "ou_1"
    assert message["session_id"] == "feishu:oc_1"
    assert message["text"] == "帮我查一下订单 O10086"


def test_feishu_card_callback_maps_confirm() -> None:
    payload = {
        "header": {"event_type": "card.action.trigger"},
        "event": {
            "action": {
                "value": {
                    "pending_action_id": "pa_1",
                    "user_id": "u_1",
                    "session_id": "s_1",
                    "confirm": "true",
                }
            }
        },
    }

    response = FeishuChannelAdapter().normalize_event(payload)

    assert response.action == "confirm_action"
    assert response.payload["next_api"] == "/api/confirm"
    assert response.payload["confirm"] is True


def test_feishu_adapter_does_not_call_policy_or_tool_gateway() -> None:
    source = inspect.getsource(FeishuChannelAdapter)

    assert "PolicyService" not in source
    assert "from app.services.tool_gateway" not in source
    assert "ToolGateway(" not in source
