from typing import Any

from fastapi import APIRouter, Depends

from app.channels.feishu_adapter import FeishuChannelAdapter


router = APIRouter()


def get_feishu_adapter() -> FeishuChannelAdapter:
    return FeishuChannelAdapter()


@router.post("/channels/feishu/events")
def handle_feishu_event(
    payload: dict[str, Any],
    adapter: FeishuChannelAdapter = Depends(get_feishu_adapter),
) -> dict[str, Any]:
    response = adapter.normalize_event(payload)
    if response.action == "challenge":
        return response.payload
    return {
        "channel": response.channel,
        "action": response.action,
        "payload": response.payload,
        "message": response.message,
    }
