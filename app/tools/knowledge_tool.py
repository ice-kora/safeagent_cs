from app.core.tool_result import ToolResult


KNOWLEDGE_BASE = {
    "七天无理由": {
        "answer": "支持符合条件的七天无理由退货，商品需保持完好且不影响二次销售。",
        "sources": ["static_policy:return_7_days"],
    },
    "退款政策": {
        "answer": "退款申请需要根据订单状态和售后规则审核，P0 阶段不会自动执行真实退款。",
        "sources": ["static_policy:refund_policy"],
    },
    "发票": {
        "answer": "如需发票，可在订单完成后提交开票信息，由人工或后续系统流程处理。",
        "sources": ["static_policy:invoice"],
    },
    "售后规则": {
        "answer": "售后请求会根据订单状态、商品状态和风险等级进入自动回复、二次确认或人工处理。",
        "sources": ["static_policy:after_sales"],
    },
}


def query_policy(query: str) -> ToolResult:
    """查询 P0 静态知识库。

    P0 暂不做真正 RAG，这里只用确定性关键词匹配，保证 Demo 和测试稳定。
    返回内容必须是公开政策摘要，不包含任何用户或订单敏感信息。
    """
    matched_entry = None
    for keyword, entry in KNOWLEDGE_BASE.items():
        if keyword in query:
            matched_entry = entry
            break

    if matched_entry is None:
        matched_entry = {
            "answer": "暂未匹配到具体政策条目，建议转人工或补充更明确的问题。",
            "sources": ["static_policy:default"],
        }

    answer = matched_entry["answer"]
    sources = matched_entry["sources"]
    return ToolResult(
        success=True,
        tool_name="knowledge_tool.query_policy",
        data={
            "answer": answer,
            "sources": sources,
        },
        summary=answer,
        safe_for_llm=True,
    )
