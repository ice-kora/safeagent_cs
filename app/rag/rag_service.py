import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.profiles import PROFILE_DEMO, get_active_profile
from app.rag.chunker import PolicyChunker
from app.rag.document_store import PolicyDocumentStore
from app.rag.chunking.chunker import TextChunker
from app.rag.document import DocumentChunk
from app.rag.embeddings.bge_m3_embedder import BgeM3Embedder
from app.rag.embeddings.mock_embedder import MockEmbedder
from app.rag.embeddings.sentence_transformer_embedder import SentenceTransformersEmbedder
from app.rag.evidence import EvidenceChunk
from app.rag.loaders import load_document_file
from app.rag.retrieval.hybrid_retriever import HybridRetriever, HybridSearchHit
from app.rag.rag_models import PolicyChunk
from app.rag.safety import sanitize_rag_payload
from app.rag.vectorstores.base import VectorStore, VectorStoreUnavailable
from app.rag.vectorstores.memory_vector_store import MemoryVectorStore
from app.rag.vectorstores.milvus_store import MilvusVectorStore


@dataclass(frozen=True)
class RagSettings:
    vector_store: str = "memory"
    milvus_uri: str | None = None
    collection: str = "safeagent_knowledge"
    top_k: int = 5
    hybrid_enabled: bool = True
    dense_weight: float = 0.7
    keyword_weight: float = 0.3
    embedding_provider: str = "mock"
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cpu"
    embedding_cache_dir: str | None = None
    vector_dimension: int = 16
    allow_dense_only: bool = False
    source_dir: str = "docs/knowledge"
    fail_fast: bool = False
    embedding_batch_size: int = 16

    @classmethod
    def from_env(cls) -> "RagSettings":
        profile = get_active_profile()
        demo_mode = profile == PROFILE_DEMO
        return cls(
            vector_store=os.getenv(
                "SAFEAGENT_RAG_VECTOR_STORE",
                "milvus" if demo_mode else "memory",
            ).lower(),
            milvus_uri=os.getenv("SAFEAGENT_RAG_MILVUS_URI"),
            collection=os.getenv("SAFEAGENT_RAG_COLLECTION", "safeagent_knowledge"),
            top_k=_int_env("SAFEAGENT_RAG_TOP_K", 5),
            hybrid_enabled=_bool_env("SAFEAGENT_RAG_HYBRID_ENABLED", True),
            dense_weight=_float_env("SAFEAGENT_RAG_DENSE_WEIGHT", 0.7),
            keyword_weight=_float_env("SAFEAGENT_RAG_KEYWORD_WEIGHT", 0.3),
            embedding_provider=os.getenv(
                "SAFEAGENT_RAG_EMBEDDING_PROVIDER",
                "bge_m3" if demo_mode else "mock",
            ).lower(),
            embedding_model=os.getenv(
                "SAFEAGENT_RAG_EMBEDDING_MODEL", "BAAI/bge-m3"
            ),
            embedding_device=os.getenv("SAFEAGENT_RAG_EMBEDDING_DEVICE", "cpu"),
            embedding_cache_dir=os.getenv("SAFEAGENT_RAG_MODEL_CACHE_DIR"),
            vector_dimension=_int_env("SAFEAGENT_RAG_VECTOR_DIMENSION", 16),
            allow_dense_only=_bool_env("SAFEAGENT_RAG_ALLOW_DENSE_ONLY", False),
            source_dir=os.getenv("SAFEAGENT_RAG_SOURCE_DIR", "docs/knowledge"),
            fail_fast=_bool_env("SAFEAGENT_RAG_FAIL_FAST", demo_mode),
            embedding_batch_size=_int_env("SAFEAGENT_RAG_EMBEDDING_BATCH_SIZE", 16),
        )


class RAGService:
    """Milvus-first / memory fallback RAG 服务。

    该服务只产出知识 evidence，不做权限裁决，也不调用业务工具。
    """

    def __init__(
        self,
        settings: RagSettings | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self.settings = settings or RagSettings.from_env()
        self.embedder = self._build_embedder()
        self.vector_store, self.vector_store_name, self.vector_store_fallback = (
            self._build_vector_store(vector_store)
        )

    def query(self, query: str) -> dict[str, Any]:
        chunks = self._load_retrieval_chunks()
        retriever = HybridRetriever(
            chunks=chunks,
            embedder=self.embedder,
            vector_store=self.vector_store,
            dense_weight=self.settings.dense_weight,
            keyword_weight=self.settings.keyword_weight,
            hybrid_enabled=self.settings.hybrid_enabled,
            index_chunks=self.vector_store_name != "milvus",
        )
        hits = retriever.retrieve(query=query, top_k=self.settings.top_k)
        useful_hits = self._filter_useful_hits(hits)
        if not useful_hits:
            return sanitize_rag_payload(
                {
                    "query": query,
                    "answer": "暂未找到相关政策，未找到足够可靠的知识依据，建议转人工客服。",
                    "evidence": [],
                    "citations": [],
                    "sources": [],
                    "matched_chunks": [],
                    "retrieval_mode": self._retrieval_mode(),
                    "embedding_model": self.embedder.model_name,
                    "vector_store": self.vector_store_name,
                    "vector_store_fallback": self.vector_store_fallback,
                    "no_answer": True,
                    "no_answer_reason": "NO_RELEVANT_EVIDENCE",
                }
            )

        evidence = [self._hit_to_evidence(hit).to_dict() for hit in useful_hits[:3]]
        citations = [
            {
                "source_id": item["doc_id"],
                "title": item["title"],
                "chunk_id": item["chunk_id"],
                "score": item["score"],
            }
            for item in evidence
        ]
        answer = self._build_answer(evidence)
        return sanitize_rag_payload(
            {
                "query": query,
                "answer": answer,
                "evidence": evidence,
                "citations": citations,
                "sources": [citation["source_id"] for citation in citations],
                "matched_chunks": [
                    {
                        "chunk_id": item["chunk_id"],
                        "text": item["content_preview"],
                        "score": item["score"],
                    }
                    for item in evidence
                ],
                "retrieval_mode": self._retrieval_mode(),
                "embedding_model": self.embedder.model_name,
                "vector_store": self.vector_store_name,
                "vector_store_fallback": self.vector_store_fallback,
                "no_answer": False,
                "no_answer_reason": None,
            }
        )

    def _filter_useful_hits(self, hits: list[HybridSearchHit]) -> list[HybridSearchHit]:
        if self.settings.allow_dense_only:
            return hits
        return [hit for hit in hits if hit.keyword_score > 0]

    def _hit_to_evidence(self, hit: HybridSearchHit) -> EvidenceChunk:
        return EvidenceChunk.from_policy_chunk(
            chunk=hit.chunk,
            score=hit.final_score,
            score_detail=hit.score_detail(),
        )

    def _build_answer(self, evidence: list[dict[str, Any]]) -> str:
        top = evidence[0]
        titles: list[str] = []
        for item in evidence:
            if item["title"] not in titles:
                titles.append(item["title"])
        return (
            f"根据《{top['title']}》：{top['content_preview']} "
            f"参考来源：{'、'.join(titles)}。"
        )

    def _retrieval_mode(self) -> str:
        return "hybrid" if self.settings.hybrid_enabled else "keyword"

    def _build_embedder(self):
        if self.settings.embedding_provider == "bge_m3":
            return BgeM3Embedder(
                model_name=self.settings.embedding_model,
                device=self.settings.embedding_device,
                cache_dir=self.settings.embedding_cache_dir,
                batch_size=self.settings.embedding_batch_size,
            )
        if self.settings.embedding_provider == "sentence_transformers":
            return SentenceTransformersEmbedder(
                model_name=self.settings.embedding_model,
                device=self.settings.embedding_device,
                cache_dir=self.settings.embedding_cache_dir,
            )
        return MockEmbedder(dimensions=self.settings.vector_dimension)

    def _build_vector_store(
        self,
        provided_store: VectorStore | None,
    ) -> tuple[VectorStore, str, str | None]:
        if provided_store is not None:
            return provided_store, provided_store.name, None
        if self.settings.vector_store == "milvus":
            try:
                dimension = self._resolve_vector_dimension()
                store = MilvusVectorStore(
                    uri=self.settings.milvus_uri,
                    collection=self.settings.collection,
                    dimension=dimension,
                )
                return store, store.name, None
            except VectorStoreUnavailable as exc:
                if self.settings.fail_fast:
                    raise
                return MemoryVectorStore(), "memory", f"milvus_unavailable: {exc}"
        return MemoryVectorStore(), "memory", None

    def _resolve_vector_dimension(self) -> int:
        if self.settings.embedding_provider == "mock":
            return self.settings.vector_dimension
        vector = self.embedder.embed(["SafeAgent-CS vector dimension probe"])[0]
        return len(vector)

    def _load_retrieval_chunks(self) -> list[PolicyChunk]:
        source_dir = Path(self.settings.source_dir)
        if source_dir.exists():
            documents = []
            for path in sorted(source_dir.rglob("*")):
                if not path.is_file():
                    continue
                try:
                    documents.extend(load_document_file(path))
                except Exception as exc:
                    if self.settings.fail_fast:
                        raise RuntimeError(
                            f"Failed to load knowledge file {path}: {exc}"
                        ) from exc
            chunks = TextChunker().split_documents(documents)
            return [_policy_chunk_from_document_chunk(chunk) for chunk in chunks]
        if self.settings.fail_fast and self.settings.vector_store == "milvus":
            raise RuntimeError(
                f"Knowledge source directory is missing: {source_dir}. "
                "Run scripts/seed_demo_knowledge.py before real demo ingest."
            )
        documents = PolicyDocumentStore().list_documents()
        return PolicyChunker().split_documents(documents)


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _policy_chunk_from_document_chunk(chunk: DocumentChunk) -> PolicyChunk:
    return PolicyChunk(
        source_id=chunk.doc_id,
        title=chunk.title,
        chunk_id=chunk.chunk_id,
        text=chunk.text,
        source=chunk.source,
        source_path=chunk.source_path,
        file_type=chunk.file_type,
        category=chunk.category,
        metadata=chunk.metadata,
    )
