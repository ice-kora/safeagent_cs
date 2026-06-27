from dataclasses import dataclass, field
from typing import Any

from app.rag.rag_models import PolicyChunk


@dataclass(frozen=True)
class EvidenceChunk:
    """RAG 对外暴露的标准 evidence 结构。"""

    doc_id: str
    chunk_id: str
    title: str
    category: str
    content_preview: str
    source: str
    source_path: str | None
    file_type: str
    score: float
    score_detail: dict[str, float | None]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "title": self.title,
            "category": self.category,
            "content_preview": self.content_preview,
            "source": self.source,
            "source_path": self.source_path,
            "file_type": self.file_type,
            "score": round(self.score, 4),
            "score_detail": {
                key: round(value, 4) if isinstance(value, float) else value
                for key, value in self.score_detail.items()
            },
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_policy_chunk(
        cls,
        chunk: PolicyChunk,
        score: float,
        score_detail: dict[str, float | None],
    ) -> "EvidenceChunk":
        preview = chunk.text
        if len(preview) > 220:
            preview = preview[:220].rstrip() + "..."
        return cls(
            doc_id=chunk.source_id,
            chunk_id=chunk.chunk_id,
            title=chunk.title,
            category=chunk.category,
            content_preview=preview,
            source=chunk.source or chunk.source_id,
            source_path=chunk.source_path,
            file_type=chunk.file_type,
            score=score,
            score_detail=score_detail,
            metadata=dict(chunk.metadata),
        )
