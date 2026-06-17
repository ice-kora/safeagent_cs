import re
from collections import Counter

from app.rag.rag_models import PolicyChunk, ScoredChunk


POLICY_TERMS = {
    "七天",
    "无理由",
    "退货",
    "退款",
    "到账",
    "时效",
    "发票",
    "开票",
    "地址",
    "改地址",
    "未发货",
    "发货",
    "物流",
    "售后",
    "人工",
    "投诉",
    "会员",
    "权益",
    "订单",
    "客服",
}

SYNONYMS = {
    "多久到账": {"到账", "时效", "退款"},
    "多久": {"时效"},
    "开发票": {"发票", "开票"},
    "开具发票": {"发票", "开票"},
    "改地址": {"地址", "改地址"},
    "修改地址": {"地址", "改地址"},
    "没发货": {"未发货", "地址", "改地址"},
    "未发货": {"未发货", "地址", "改地址"},
    "发货后": {"发货", "物流"},
    "七天无理由": {"七天", "无理由", "退货"},
}


class KeywordRetriever:
    """标准库实现的轻量关键词检索器。"""

    def __init__(self, chunks: list[PolicyChunk]) -> None:
        self.chunks = chunks

    def retrieve(self, query: str, top_k: int = 3) -> list[ScoredChunk]:
        query_terms = _extract_query_terms(query)
        if not query_terms:
            return []

        scored: list[ScoredChunk] = []
        for chunk in self.chunks:
            score = _score_chunk(query_terms, chunk)
            if score > 0:
                scored.append(ScoredChunk(chunk=chunk, score=score))
        return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]


def _extract_query_terms(query: str) -> set[str]:
    normalized = query.lower()
    terms = {term for term in POLICY_TERMS if term in normalized}
    for phrase, phrase_terms in SYNONYMS.items():
        if phrase in normalized:
            terms.update(phrase_terms)
    terms.update(re.findall(r"[a-zA-Z0-9_]{2,}", normalized))
    return terms


def _score_chunk(query_terms: set[str], chunk: PolicyChunk) -> float:
    text = f"{chunk.title} {chunk.text}".lower()
    title = chunk.title.lower()
    term_counts = Counter(term for term in query_terms if term in text)
    if not term_counts:
        return 0.0
    score = 0.0
    for term, count in term_counts.items():
        score += count
        if term in title:
            score += 1.5
    # “未发货/没发货”和“发货后”是地址修改政策里的关键分界线。
    # 轻量检索没有语义模型，因此对精确时态做小幅加权，避免相反规则排到第一。
    if "未发货" in query_terms and "未发货" in text:
        score += 2.0
    if "未发货" in query_terms and "发货后" in title:
        score -= 0.8
    return score / max(len(query_terms), 1)
