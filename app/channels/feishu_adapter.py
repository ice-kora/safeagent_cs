import json
from typing import Any

from app.channels.base import ChannelResponse, NormalizedMessage
from app.services.logging_service import LoggingService


class FeishuChannelAdapter:
    """Feishu 入口 skeleton。

    只处理 challenge、消息标准化和卡片 callback 映射；不做 Policy，也不
    直接调用 ToolGateway。
    """

    channel = "feishu"

    def normalize_event(self, payload: dict[str, Any]) -> ChannelResponse:
        if "challenge" in payload:
            return ChannelResponse(
                channel=self.channel,
                action="challenge",
                payload={"challenge": payload["challenge"]},
                message="challenge accepted",
            )

        header = payload.get("header") or {}
        event = payload.get("event") or {}
        event_type = str(header.get("event_type") or payload.get("type") or "")
        if "card.action.trigger" in event_type:
            return self._normalize_card_callback(event, event_type)
        if "im.message.receive" in event_type or "message" in event:
            message = self._normalize_message(event, event_type)
            return ChannelResponse(
                channel=self.channel,
                action="chat_message",
                payload={"message": message.__dict__, "next_api": "/api/chat"},
                message="message normalized",
            )
        return ChannelResponse(
            channel=self.channel,
            action="ignored",
            payload={"event_type": event_type},
            message="unsupported feishu event",
        )

    def _normalize_message(
        self,
        event: dict[str, Any],
        event_type: str,
    ) -> NormalizedMessage:
        message = event.get("message") or {}
        sender = event.get("sender") or {}
        sender_id = sender.get("sender_id") or {}
        user_id = (
            sender_id.get("user_id")
            or sender_id.get("open_id")
            or event.get("user_id")
            or "feishu_unknown_user"
        )
        message_id = str(message.get("message_id") or event.get("message_id") or "")
        chat_id = str(message.get("chat_id") or event.get("chat_id") or user_id)
        text = self._extract_text(message.get("content"))
        return NormalizedMessage(
            channel=self.channel,
            message_id=message_id or f"feishu_msg_{chat_id}",
            user_id=str(user_id),
            session_id=f"feishu:{chat_id}",
            text=text,
            raw_event_type=event_type,
            metadata=LoggingService.sanitize_payload(
                {
                    "chat_id": chat_id,
                    "message_type": message.get("message_type"),
                    "dedupe_key": message_id,
                }
            ),
        )

    def _normalize_card_callback(
        self,
        event: dict[str, Any],
        event_type: str,
    ) -> ChannelResponse:
        action = event.get("action") or {}
        value = action.get("value") or {}
        confirm = str(value.get("confirm", "")).lower() in {"true", "1", "yes"}
        mapped_action = "confirm_action" if confirm else "cancel_action"
        return ChannelResponse(
            channel=self.channel,
            action=mapped_action,
            payload={
                "next_api": "/api/confirm",
                "pending_action_id": value.get("pending_action_id"),
                "user_id": value.get("user_id"),
                "session_id": value.get("session_id"),
                "confirm": confirm,
                "raw_event_type": event_type,
            },
            message="card callback normalized",
        )

    @staticmethod
    def _extract_text(content: Any) -> str:
        if isinstance(content, str):
            try:
                payload = json.loads(content)
            except json.JSONDecodeError:
                return content
        elif isinstance(content, dict):
            payload = content
        else:
            return ""
        text = payload.get("text")
        return text if isinstance(text, str) else ""
