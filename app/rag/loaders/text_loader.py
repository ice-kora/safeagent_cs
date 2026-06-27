from pathlib import Path

from app.rag.document import KnowledgeDocument
from app.rag.loaders.base import build_document


class TextLoader:
    supported_extensions = frozenset({".txt"})

    def load(self, path: str | Path) -> list[KnowledgeDocument]:
        content = Path(path).read_text(encoding="utf-8")
        return [build_document(path, content, file_type="txt")]
