from pathlib import Path

from app.core.tool_result import ToolError, ToolResult
from app.services.repository_service import RepositoryService


def query_order(
    order_id: str,
    mock_dir: str | Path | None = None,
    db_path: str | Path | None = None,
) -> ToolResult:
    """查询订单脱敏摘要。

    工具层不返回完整订单对象，只暴露回复用户需要的安全字段。真实权限判断
    已由 PolicyService 负责，本工具仍保持最小输出，避免后续日志或 LLM 摘要
    意外拿到手机号、完整地址、支付信息。
    """
    repository = RepositoryService(mock_dir=mock_dir, db_path=db_path)
    order_context = repository.get_order_auth_context(order_id)
    if not order_context:
        return ToolResult(
            success=False,
            tool_name="order_tool.query_order",
            data={},
            summary="未找到对应订单。",
            error_type="ORDER_NOT_FOUND",
            safe_for_llm=True,
            error=ToolError(
                failure_type="ORDER_NOT_FOUND",
                message="订单不存在或不可查询",
                retryable=False,
            ),
        )

    safe_summary = (
        f"订单 {order_context['order_id']} 当前状态为"
        f"{order_context.get('order_status')}，配送状态为"
        f"{order_context.get('delivery_status')}，退款状态为"
        f"{order_context.get('refund_status')}。"
    )
    return ToolResult(
        success=True,
        tool_name="order_tool.query_order",
        data={
            "order_id": order_context["order_id"],
            "order_status": order_context.get("order_status"),
            "delivery_status": order_context.get("delivery_status"),
            "refund_status": order_context.get("refund_status"),
            "safe_summary": safe_summary,
        },
        summary=safe_summary,
        safe_for_llm=True,
    )


def change_address(
    order_id: str,
    new_address: str | None = None,
    mock_dir: str | Path | None = None,
    db_path: str | Path | None = None,
) -> ToolResult:
    """接收地址修改请求，但 P0 不真实修改订单数据。

    地址属于敏感信息，即使调用方传入 new_address，也不能写入返回结果或
    mock_orders.json。真正修改动作会在后续确认链路和真实业务系统中处理。
    """
    repository = RepositoryService(mock_dir=mock_dir, db_path=db_path)
    order_context = repository.get_order_auth_context(order_id)
    if not order_context:
        return ToolResult(
            success=False,
            tool_name="order_tool.change_address",
            data={},
            summary="未找到对应订单，无法接收地址修改请求。",
            error_type="ORDER_NOT_FOUND",
            safe_for_llm=True,
            error=ToolError(
                failure_type="ORDER_NOT_FOUND",
                message="订单不存在或不可修改",
                retryable=False,
            ),
        )

    summary = f"订单 {order_context['order_id']} 的地址修改请求已接收，等待确认后处理。"
    return ToolResult(
        success=True,
        tool_name="order_tool.change_address",
        data={
            "order_id": order_context["order_id"],
            "request_status": "RECEIVED",
            "safe_summary": summary,
        },
        summary=summary,
        safe_for_llm=True,
    )
