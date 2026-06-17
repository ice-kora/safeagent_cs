import re

from app.rag.rag_models import PolicyChunk, PolicyDocument


class PolicyChunker:
    """将政策文档切分为可检索片段。

    MVP 使用段落/句子级切分，不引入复杂 NLP 或外部依赖。
    """

    def __init__(self, max_chars: int = 160) -> None:
        self.max_chars = max_chars

    def split_documents(self, documents: list[PolicyDocument]) -> list[PolicyChunk]:
        chunks: list[PolicyChunk] = []
        for document in documents:
            parts = self._split_text(document.content)
            for index, part in enumerate(parts, start=1):
                chunks.append(
                    PolicyChunk(
                        source_id=document.source_id,
                        title=document.title,
                        chunk_id=f"{document.source_id}#chunk_{index}",
                        text=part,
                    )
                )
        return chunks

    def _split_text(self, text: str) -> list[str]:
        paragraphs = [
            part.strip()
            for part in re.split(r"(?:\n+|(?<=[。！？]))", text)
            if part.strip()
        ]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if not current:
                current = paragraph
                continue
            if len(current) + len(paragraph) <= self.max_chars:
                current += paragraph
            else:
                chunks.append(current)
                current = paragraph
        if current:
            chunks.append(current)
        return chunks

