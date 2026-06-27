import json
from pathlib import Path

from app.rag.evaluation.metrics import compute_retrieval_metrics
from app.rag.loaders import load_document_file
from app.rag.rag_service import RAGService, RagSettings


def test_rag_service_returns_standard_evidence_fields(monkeypatch) -> None:
    monkeypatch.setenv("SAFEAGENT_RAG_VECTOR_STORE", "memory")
    monkeypatch.setenv("SAFEAGENT_RAG_EMBEDDING_PROVIDER", "mock")

    result = RAGService().query("订单未发货可以修改地址吗")

    assert result["no_answer"] is False
    assert result["retrieval_mode"] == "hybrid"
    assert result["vector_store"] == "memory"
    assert result["evidence"]
    evidence = result["evidence"][0]
    assert {
        "doc_id",
        "chunk_id",
        "title",
        "category",
        "content_preview",
        "source",
        "source_path",
        "file_type",
        "score",
        "score_detail",
        "metadata",
    }.issubset(evidence)
    assert {
        "dense_score",
        "keyword_score",
        "hybrid_score",
        "rerank_score",
        "final_score",
    }.issubset(evidence["score_detail"])
    assert result["citations"]
    assert result["sources"]
    assert result["matched_chunks"]


def test_rag_service_returns_no_answer_for_irrelevant_query(monkeypatch) -> None:
    monkeypatch.setenv("SAFEAGENT_RAG_VECTOR_STORE", "memory")

    result = RAGService().query("我要预订火星基地酒店")

    assert result["no_answer"] is True
    assert result["no_answer_reason"] == "NO_RELEVANT_EVIDENCE"
    assert result["evidence"] == []
    assert result["citations"] == []


def test_milvus_unavailable_falls_back_to_memory() -> None:
    settings = RagSettings(vector_store="milvus", milvus_uri=None)

    result = RAGService(settings=settings).query("七天无理由退货")

    assert result["vector_store"] == "memory"
    assert "milvus_unavailable" in result["vector_store_fallback"]


def test_document_loaders_support_text_markdown_html_and_csv(tmp_path: Path) -> None:
    txt = tmp_path / "policy.txt"
    md = tmp_path / "policy.md"
    html = tmp_path / "policy.html"
    csv = tmp_path / "policy.csv"
    txt.write_text("七天无理由退货", encoding="utf-8")
    md.write_text("# 地址修改\n订单未发货可以改地址", encoding="utf-8")
    html.write_text("<html><body><h1>退款</h1><p>1 到 3 个工作日</p></body></html>", encoding="utf-8")
    csv.write_text("title,content\n会员,优先客服", encoding="utf-8")

    assert load_document_file(txt)[0].file_type == "txt"
    assert load_document_file(md)[0].file_type == "md"
    assert "退款" in load_document_file(html)[0].content
    assert "会员 | 优先客服" in load_document_file(csv)[0].content


def test_rag_eval_metrics_shape() -> None:
    results = [
        {
            "expected_source_ids": ["policy_return_7d"],
            "sources": ["policy_return_7d"],
            "no_answer_expected": False,
            "no_answer": False,
            "dense_sources": ["policy_return_7d"],
            "keyword_sources": ["policy_return_7d"],
        },
        {
            "expected_source_ids": [],
            "sources": [],
            "no_answer_expected": True,
            "no_answer": True,
            "dense_sources": [],
            "keyword_sources": [],
        },
    ]

    metrics = compute_retrieval_metrics(results)

    assert metrics["total_cases"] == 2
    assert metrics["hit@1"] == 0.5
    assert metrics["hit@3"] == 0.5
    assert metrics["no_answer_accuracy"] == 1.0


def test_eval_cases_have_at_least_30_cases() -> None:
    cases = json.loads(
        (Path(__file__).parent / "evals" / "rag_cases.json").read_text(
            encoding="utf-8"
        )
    )

    assert len(cases) >= 30
