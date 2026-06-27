from app.core.tool_result import ToolError, ToolResult
from app.rag.rag_service import RAGService
from app.rag.safety import sanitize_rag_payload


def query_policy(query: str) -> ToolResult:
    """查询本地 RAG 政策知识库。

    RAG 只作为 knowledge_tool.query_policy 的内部实现。它不判断权限、
    不调用业务工具，也不生成真实业务动作；主链路仍必须经过 ToolGateway。
    """
    try:
        data = RAGService().query(query)
    except Exception:
        return ToolResult(
            success=False,
            tool_name="knowledge_tool.query_policy",
            data={},
            summary="政策知识库查询失败。",
            error_type="RAG_QUERY_FAILED",
            safe_for_llm=True,
            error=ToolError(
                failure_type="RAG_QUERY_FAILED",
                message="政策知识库查询失败",
                retryable=False,
            ),
        )

    if data.get("no_answer"):
        answer = data.get("answer") or "未找到足够可靠的知识依据，建议转人工客服。"
        return ToolResult(
            success=False,
            tool_name="knowledge_tool.query_policy",
            data=sanitize_rag_payload(data),
            summary=answer,
            error_type="POLICY_NOT_FOUND",
            safe_for_llm=True,
            error=ToolError(
                failure_type="POLICY_NOT_FOUND",
                message="未找到相关政策",
                retryable=False,
            ),
        )

    answer = data.get("answer") or "已查询政策知识库。"
    return ToolResult(
        success=True,
        tool_name="knowledge_tool.query_policy",
        data=data,
        summary=sanitize_rag_payload(answer),
        safe_for_llm=True,
    )
