from pathlib import Path

from app.rag.document import KnowledgeDocument
from app.rag.loaders.base import build_document


class PdfLoader:
    supported_extensions = frozenset({".pdf"})

    def load(self, path: str | Path) -> list[KnowledgeDocument]:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("pypdf is required to load PDF knowledge files") from exc
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return [build_document(path, text, file_type="pdf")]
