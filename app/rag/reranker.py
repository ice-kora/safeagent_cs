from app.rag.rag_models import ScoredChunk


def rerank_chunks(chunks: list[ScoredChunk], top_k: int = 3) -> list[ScoredChunk]:
    """按分数重排并截断 top_k。"""
    return sorted(chunks, key=lambda item: item.score, reverse=True)[:top_k]

