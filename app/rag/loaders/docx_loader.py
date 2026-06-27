from pathlib import Path

from app.rag.document import KnowledgeDocument
from app.rag.loaders.base import build_document


class DocxLoader:
    supported_extensions = frozenset({".docx"})

    def load(self, path: str | Path) -> list[KnowledgeDocument]:
        try:
            import docx
        except ImportError as exc:
            raise RuntimeError("python-docx is required to load DOCX knowledge files") from exc
        document = docx.Document(str(path))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        return [build_document(path, text, file_type="docx")]
