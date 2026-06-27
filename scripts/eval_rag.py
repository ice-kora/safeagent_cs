import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.evaluation.metrics import compute_retrieval_metrics
from app.rag.rag_service import RAGService


CASES_PATH = PROJECT_ROOT / "tests" / "evals" / "rag_cases.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SafeAgent-CS RAG eval")
    parser.add_argument("--cases", default=str(CASES_PATH))
    parser.add_argument("--vector-store", choices=["memory", "milvus"], default=None)
    parser.add_argument("--embedding", choices=["mock", "sentence_transformers", "bge_m3"], default=None)
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--collection", default=None)
    parser.add_argument("--source", default=None)
    args = parser.parse_args()

    _apply_overrides(args)
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    if len(cases) < 30:
        print(f"[ERROR] RAG eval requires at least 30 cases, got {len(cases)}.")
        return 1

    try:
        service = RAGService()
    except Exception as exc:
        print(f"[ERROR] Failed to initialize RAGService: {exc}")
        return 1

    results = []
    for case in cases:
        try:
            response = service.query(case["query"])
        except Exception as exc:
            print(f"[ERROR] RAG query failed for {case['query']!r}: {exc}")
            return 1
        evidence = response.get("evidence", [])
        results.append(
            {
                "query": case["query"],
                "expected_source_ids": case["expected_source_ids"],
                "no_answer_expected": case.get("no_answer_expected", False),
                "sources": response.get("sources", []),
                "no_answer": response.get("no_answer", False),
                "retrieval_mode": response.get("retrieval_mode"),
                "embedding_model": response.get("embedding_model"),
                "vector_store": response.get("vector_store"),
                "vector_store_fallback": response.get("vector_store_fallback"),
                "top_k": [
                    {
                        "doc_id": item.get("doc_id"),
                        "chunk_id": item.get("chunk_id"),
                        "title": item.get("title"),
                        "score": item.get("score"),
                        "score_detail": item.get("score_detail"),
                        "content_preview": item.get("content_preview"),
                    }
                    for item in evidence
                ],
                "dense_sources": _sources_by_score(response, "dense_score"),
                "keyword_sources": _sources_by_score(response, "keyword_score"),
            }
        )
    output = {
        "metrics": compute_retrieval_metrics(results),
        "cases": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def _apply_overrides(args) -> None:
    if args.vector_store:
        os.environ["SAFEAGENT_RAG_VECTOR_STORE"] = args.vector_store
    if args.embedding:
        os.environ["SAFEAGENT_RAG_EMBEDDING_PROVIDER"] = args.embedding
    if args.top_k:
        os.environ["SAFEAGENT_RAG_TOP_K"] = str(args.top_k)
    if args.collection:
        os.environ["SAFEAGENT_RAG_COLLECTION"] = args.collection
    if args.source:
        os.environ["SAFEAGENT_RAG_SOURCE_DIR"] = args.source
    if args.vector_store == "milvus" or args.embedding == "bge_m3":
        os.environ["SAFEAGENT_RAG_FAIL_FAST"] = "true"
        os.environ.setdefault("SAFEAGENT_RAG_HYBRID_ENABLED", "true")


def _sources_by_score(response: dict, score_name: str) -> list[str]:
    evidence = response.get("evidence") or []
    ranked = sorted(
        evidence,
        key=lambda item: item.get("score_detail", {}).get(score_name) or 0,
        reverse=True,
    )
    return [item["doc_id"] for item in ranked]


if __name__ == "__main__":
    raise SystemExit(main())
