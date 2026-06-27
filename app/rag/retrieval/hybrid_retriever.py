from dataclasses import dataclass

from app.rag.embeddings.base import Embedder
from app.rag.rag_models import PolicyChunk
from app.rag.retrieval.query_rewriter import rewrite_query
from app.rag.retriever import KeywordRetriever
from app.rag.vectorstores.base import VectorRecord, VectorStore


@dataclass(frozen=True)
class HybridSearchHit:
    chunk: PolicyChunk
    dense_score: float
    keyword_score: float
    hybrid_score: float
    final_score: float

    def score_detail(self) -> dict[str, float | None]:
        return {
            "dense_score": self.dense_score,
            "keyword_score": self.keyword_score,
            "hybrid_score": self.hybrid_score,
            "rerank_score": None,
            "final_score": self.final_score,
        }


class HybridRetriever:
    """dense + keyword 的第一版融合检索。"""

    def __init__(
        self,
        *,
        chunks: list[PolicyChunk],
        embedder: Embedder,
        vector_store: VectorStore,
        dense_weight: float = 0.7,
        keyword_weight: float = 0.3,
        hybrid_enabled: bool = True,
        index_chunks: bool = True,
    ) -> None:
        self.chunks = chunks
        self.embedder = embedder
        self.vector_store = vector_store
        self.dense_weight = dense_weight
        self.keyword_weight = keyword_weight
        self.hybrid_enabled = hybrid_enabled
        self._chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        if index_chunks:
            self._index_chunks()

    def retrieve(self, query: str, top_k: int) -> list[HybridSearchHit]:
        rewritten = rewrite_query(query)
        keyword_hits = KeywordRetriever(self.chunks).retrieve(
            query=rewritten,
            top_k=max(top_k, len(self.chunks)),
        )
        keyword_scores = _normalize_scores(
            {item.chunk.chunk_id: item.score for item in keyword_hits}
        )

        query_vector = self.embedder.embed([rewritten])[0]
        dense_hits = self.vector_store.search(
            query_vector=query_vector,
            top_k=max(top_k, len(self.chunks), 1),
        )
        dense_scores = _normalize_scores(self._dense_scores_by_chunk_id(dense_hits))

        chunk_ids = set(keyword_scores) | set(dense_scores)
        hits: list[HybridSearchHit] = []
        for chunk_id in chunk_ids:
            dense_score = dense_scores.get(chunk_id, 0.0)
            keyword_score = keyword_scores.get(chunk_id, 0.0)
            if self.hybrid_enabled:
                hybrid_score = (
                    self.dense_weight * dense_score
                    + self.keyword_weight * keyword_score
                )
            else:
                hybrid_score = keyword_score
            if hybrid_score <= 0:
                continue
            hits.append(
                HybridSearchHit(
                    chunk=self._chunk_by_id[chunk_id],
                    dense_score=dense_score,
                    keyword_score=keyword_score,
                    hybrid_score=hybrid_score,
                    final_score=hybrid_score,
                )
            )
        return sorted(hits, key=lambda item: item.final_score, reverse=True)[:top_k]

    def _index_chunks(self) -> None:
        if not self.chunks:
            return
        vectors = self.embedder.embed([f"{chunk.title}\n{chunk.text}" for chunk in self.chunks])
        records = [
            VectorRecord(
                id=chunk.chunk_id,
                vector=vector,
                payload={
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.source_id,
                    "title": chunk.title,
                    "source": chunk.source_id,
                    "source_path": chunk.source_path,
                    "file_type": chunk.file_type,
                    "category": chunk.category,
                    "content": chunk.text,
                    "content_preview": chunk.text[:220],
                    "metadata": chunk.metadata,
                },
            )
            for chunk, vector in zip(self.chunks, vectors, strict=True)
        ]
        self.vector_store.upsert(records)

    def _dense_scores_by_chunk_id(self, dense_hits) -> dict[str, float]:
        scores: dict[str, float] = {}
        for item in dense_hits:
            chunk_id = str(item.payload.get("chunk_id") or item.id)
            if chunk_id not in self._chunk_by_id:
                self._chunk_by_id[chunk_id] = _chunk_from_payload(chunk_id, item.payload)
            scores[chunk_id] = item.score
        return scores


def _normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    max_score = max(scores.values()) or 1.0
    return {key: max(0.0, value / max_score) for key, value in scores.items()}


def _chunk_from_payload(chunk_id: str, payload: dict) -> PolicyChunk:
    doc_id = str(payload.get("doc_id") or payload.get("source") or chunk_id)
    content = str(payload.get("content") or payload.get("content_preview") or "")
    return PolicyChunk(
        source_id=doc_id,
        title=str(payload.get("title") or doc_id),
        chunk_id=chunk_id,
        text=content,
        source=str(payload.get("source") or doc_id),
        source_path=payload.get("source_path") or None,
        file_type=str(payload.get("file_type") or "text"),
        category=str(payload.get("category") or "policy"),
        metadata=dict(payload.get("metadata") or {}),
    )
