from app.rag.retriever import SYNONYMS


def rewrite_query(query: str) -> str:
    """轻量 query rewrite：把已知同义词追加到查询文本中。"""

    additions: list[str] = []
    normalized = query.lower()
    for phrase, terms in SYNONYMS.items():
        if phrase in normalized:
            additions.extend(sorted(terms))
    if not additions:
        return query
    return f"{query} {' '.join(additions)}"
