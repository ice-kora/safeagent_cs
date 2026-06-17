from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyDocument:
    """政策原始文档。"""

    source_id: str
    title: str
    content: str


@dataclass(frozen=True)
class PolicyChunk:
    """可检索的政策切片。"""

    source_id: str
    title: str
    chunk_id: str
    text: str


@dataclass(frozen=True)
class ScoredChunk:
    """带检索分数的切片。"""

    chunk: PolicyChunk
    score: float

    def citation_dict(self) -> dict[str, object]:
        return {
            "source_id": self.chunk.source_id,
            "title": self.chunk.title,
            "chunk_id": self.chunk.chunk_id,
            "score": round(self.score, 4),
        }

    def matched_chunk_dict(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk.chunk_id,
            "text": self.chunk.text,
            "score": round(self.score, 4),
        }

