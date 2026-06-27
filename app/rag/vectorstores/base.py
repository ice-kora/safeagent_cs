from dataclasses import dataclass, field
from typing import Any, Protocol


class VectorStoreUnavailable(RuntimeError):
    """向量库不可用，调用方可降级到 MemoryVectorStore。"""


@dataclass(frozen=True)
class VectorRecord:
    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VectorSearchResult:
    id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


class VectorStore(Protocol):
    name: str

    def upsert(self, records: list[VectorRecord]) -> None:
        ...

    def search(self, query_vector: list[float], top_k: int) -> list[VectorSearchResult]:
        ...
