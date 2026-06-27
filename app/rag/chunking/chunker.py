from app.rag.document import DocumentChunk, KnowledgeDocument


class TextChunker:
    """简单文本切片器，用于导入知识库文件。"""

    def __init__(self, chunk_size: int = 500, overlap: int = 80) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split_documents(self, documents: list[KnowledgeDocument]) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        for document in documents:
            text = document.content.strip()
            if not text:
                continue
            start = 0
            index = 0
            while start < len(text):
                end = min(start + self.chunk_size, len(text))
                chunks.append(
                    DocumentChunk(
                        doc_id=document.doc_id,
                        chunk_id=f"{document.doc_id}#{index}",
                        title=document.title,
                        text=text[start:end],
                        source=document.source,
                        source_path=document.source_path,
                        file_type=document.file_type,
                        category=document.category,
                        metadata=document.metadata,
                    )
                )
                if end == len(text):
                    break
                start = max(end - self.overlap, start + 1)
                index += 1
        return chunks
