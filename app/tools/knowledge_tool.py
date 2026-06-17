from app.core.tool_result import ToolError, ToolResult
from app.rag.chunker import PolicyChunker
from app.rag.document_store import PolicyDocumentStore
from app.rag.reranker import rerank_chunks
from app.rag.retriever import KeywordRetriever
from app.rag.safety import sanitize_rag_payload


def query_policy(query: str) -> ToolResult:
    """查询本地 RAG 政策知识库。

    RAG 只作为 knowledge_tool.query_policy 的内部实现。它不判断权限、
    不调用业务工具，也不生成真实业务动作；主链路仍必须经过 ToolGateway。
    """
    try:
        documents = PolicyDocumentStore().list_documents()
        chunks = PolicyChunker().split_documents(documents)
        retrieved = KeywordRetriever(chunks).retrieve(query=query, top_k=5)
        reranked = rerank_chunks(retrieved, top_k=3)
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

    safe_query = sanitize_rag_payload(query)
    if not reranked:
        answer = "暂未找到相关政策，建议补充更明确的问题或转人工处理。"
        data = {
            "query": safe_query,
            "answer": answer,
            "citations": [],
            "sources": [],
            "matched_chunks": [],
        }
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

    answer = _build_answer(reranked)
    citations = [item.citation_dict() for item in reranked]
    matched_chunks = [item.matched_chunk_dict() for item in reranked]
    data = sanitize_rag_payload(
        {
            "query": safe_query,
            "answer": answer,
            "citations": citations,
            # sources 保留旧字段，兼容已有 Demo 和测试。
            "sources": [citation["source_id"] for citation in citations],
            "matched_chunks": matched_chunks,
        }
    )
    return ToolResult(
        success=True,
        tool_name="knowledge_tool.query_policy",
        data=data,
        summary=sanitize_rag_payload(answer),
        safe_for_llm=True,
    )


def _build_answer(scored_chunks) -> str:
    """基于命中切片生成规则摘要，不调用 LLM。"""
    top_chunk = scored_chunks[0].chunk
    supporting_titles = []
    for item in scored_chunks:
        if item.chunk.title not in supporting_titles:
            supporting_titles.append(item.chunk.title)
    evidence = top_chunk.text
    if len(evidence) > 180:
        evidence = evidence[:180].rstrip() + "..."
    return f"根据《{top_chunk.title}》：{evidence} 参考来源：{'、'.join(supporting_titles)}。"
