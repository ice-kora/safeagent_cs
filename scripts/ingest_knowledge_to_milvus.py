import argparse
import json
import sys
import time
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.chunking.chunker import TextChunker
from app.rag.document import DocumentChunk, KnowledgeDocument
from app.rag.embeddings.bge_m3_embedder import BgeM3Embedder
from app.rag.loaders import load_document_file
from app.rag.rag_service import RagSettings
from app.rag.vectorstores.base import VectorRecord
from app.rag.vectorstores.milvus_store import MilvusVectorStore


SUPPORTED_INGEST_EXTENSIONS = {
    ".md",
    ".txt",
    ".pdf",
    ".docx",
    ".csv",
    ".xlsx",
    ".html",
    ".htm",
}


def main() -> int:
    settings = RagSettings.from_env()
    parser = argparse.ArgumentParser(description="Ingest knowledge docs into Milvus")
    parser.add_argument("--source", default=settings.source_dir)
    parser.add_argument("--collection", default=settings.collection)
    parser.add_argument("--milvus-uri", default=settings.milvus_uri)
    parser.add_argument("--embedding-model", default=settings.embedding_model)
    parser.add_argument("--embedding-device", default=settings.embedding_device)
    parser.add_argument("--cache-dir", default=settings.embedding_cache_dir)
    parser.add_argument("--batch-size", type=int, default=settings.embedding_batch_size)
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--overlap", type=int, default=80)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--top-k", type=int, default=settings.top_k)
    args = parser.parse_args()

    if not args.milvus_uri:
        print("[ERROR] SAFEAGENT_RAG_MILVUS_URI or --milvus-uri is required.")
        return 1

    started = time.perf_counter()
    source = Path(args.source)
    documents = load_knowledge_documents(source)
    if not documents:
        print(f"[ERROR] No supported knowledge documents found under {source}.")
        return 1

    chunks = TextChunker(chunk_size=args.chunk_size, overlap=args.overlap).split_documents(
        documents
    )
    if not chunks:
        print("[ERROR] Loaded documents produced zero chunks.")
        return 1

    embedder = BgeM3Embedder(
        model_name=args.embedding_model,
        device=args.embedding_device,
        cache_dir=args.cache_dir,
        batch_size=args.batch_size,
    )
    vectors = embedder.embed([f"{chunk.title}\n{chunk.text}" for chunk in chunks])
    vector_dim = len(vectors[0]) if vectors else 0
    if vector_dim <= 0:
        print("[ERROR] Embedding model returned empty dense vectors.")
        return 1

    store = MilvusVectorStore(
        uri=args.milvus_uri,
        collection=args.collection,
        dimension=vector_dim,
        auto_create=False,
    )
    if args.reset:
        store.rebuild_collection(vector_dim)
    else:
        store.ensure_collection(vector_dim)
    store.upsert(_records_from_chunks(chunks, vectors))

    elapsed = round(time.perf_counter() - started, 3)
    result = {
        "documents_count": len(documents),
        "chunks_count": len(chunks),
        "embedding_model": args.embedding_model,
        "vector_dim": vector_dim,
        "collection_name": args.collection,
        "milvus_uri": args.milvus_uri,
        "ingest_time_seconds": elapsed,
        "top_k": args.top_k,
        "collection": store.collection_stats(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def load_knowledge_documents(source: Path) -> list[KnowledgeDocument]:
    if not source.exists():
        raise RuntimeError(f"Knowledge source directory does not exist: {source}")
    documents: list[KnowledgeDocument] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_INGEST_EXTENSIONS:
            continue
        documents.extend(load_document_file(path))
    return documents


def _records_from_chunks(
    chunks: list[DocumentChunk],
    vectors: list[list[float]],
) -> list[VectorRecord]:
    return [
        VectorRecord(
            id=chunk.chunk_id,
            vector=vector,
            payload={
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "title": chunk.title,
                "source": chunk.source,
                "source_path": chunk.source_path,
                "file_type": chunk.file_type,
                "category": chunk.category,
                "content": chunk.text,
                "content_preview": _preview(chunk.text),
                "metadata": chunk.metadata,
            },
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]


def _batched(items: list[VectorRecord], size: int) -> Iterable[list[VectorRecord]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _preview(text: str) -> str:
    stripped = text.strip()
    return stripped[:220] + ("..." if len(stripped) > 220 else "")


if __name__ == "__main__":
    raise SystemExit(main())
