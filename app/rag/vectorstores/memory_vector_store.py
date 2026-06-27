import math

from app.rag.vectorstores.base import VectorRecord, VectorSearchResult


class MemoryVectorStore:
    """内存向量库，作为测试和 Milvus 不可用时的安全 fallback。"""

    name = "memory"

    def __init__(self) -> None:
        self._records: dict[str, VectorRecord] = {}

    def upsert(self, records: list[VectorRecord]) -> None:
        for record in records:
            self._records[record.id] = record

    def search(self, query_vector: list[float], top_k: int) -> list[VectorSearchResult]:
        scored = [
            VectorSearchResult(
                id=record.id,
                score=_cosine(query_vector, record.vector),
                payload=record.payload,
            )
            for record in self._records.values()
        ]
        return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    denominator = left_norm * right_norm
    if denominator == 0:
        return 0.0
    return max(0.0, numerator / denominator)
