from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class NormalizedMessage:
    channel: str
    message_id: str
    user_id: str
    session_id: str
    text: str
    raw_event_type: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChannelResponse:
    channel: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    message: str = ""


class ChannelAdapter(Protocol):
    channel: str

    def normalize_event(self, payload: dict[str, Any]) -> ChannelResponse:
        ...
