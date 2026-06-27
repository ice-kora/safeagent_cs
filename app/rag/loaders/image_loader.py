from pathlib import Path

from app.rag.document import KnowledgeDocument


class ImageLoader:
    supported_extensions = frozenset({".png", ".jpg", ".jpeg", ".webp"})

    def load(self, path: str | Path) -> list[KnowledgeDocument]:
        raise RuntimeError("Image OCR ingestion is intentionally disabled in v1.0")
