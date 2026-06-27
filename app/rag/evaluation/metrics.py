from dataclasses import dataclass


@dataclass(frozen=True)
class RagEvalCase:
    query: str
    expected_source_ids: list[str]
    no_answer_expected: bool = False


def compute_retrieval_metrics(results: list[dict]) -> dict[str, float | int]:
    """计算轻量 RAG eval 指标。"""

    total = len(results)
    if total == 0:
        return {
            "total_cases": 0,
            "hit@1": 0.0,
            "hit@3": 0.0,
            "recall@5": 0.0,
            "mrr@3": 0.0,
            "no_answer_accuracy": 0.0,
            "dense_hit@3": 0.0,
            "keyword_hit@3": 0.0,
            "hybrid_hit@3": 0.0,
        }

    hit1 = hit3 = recall5 = mrr3 = no_answer_ok = 0.0
    dense_hit3 = keyword_hit3 = hybrid_hit3 = 0.0
    for item in results:
        expected = set(item.get("expected_source_ids") or [])
        sources = item.get("sources") or []
        no_answer_expected = bool(item.get("no_answer_expected"))
        no_answer = bool(item.get("no_answer"))
        if no_answer == no_answer_expected:
            no_answer_ok += 1
        if not expected:
            continue
        if sources[:1] and sources[0] in expected:
            hit1 += 1
        if any(source in expected for source in sources[:3]):
            hit3 += 1
            hybrid_hit3 += 1
        recall5 += len(expected.intersection(sources[:5])) / max(len(expected), 1)
        for rank, source in enumerate(sources[:3], start=1):
            if source in expected:
                mrr3 += 1 / rank
                break
        if any(source in expected for source in item.get("dense_sources", [])[:3]):
            dense_hit3 += 1
        if any(source in expected for source in item.get("keyword_sources", [])[:3]):
            keyword_hit3 += 1

    return {
        "total_cases": total,
        "hit@1": hit1 / total,
        "hit@3": hit3 / total,
        "recall@5": recall5 / total,
        "mrr@3": mrr3 / total,
        "no_answer_accuracy": no_answer_ok / total,
        "dense_hit@3": dense_hit3 / total,
        "keyword_hit@3": keyword_hit3 / total,
        "hybrid_hit@3": hybrid_hit3 / total,
    }
