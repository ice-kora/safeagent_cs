from pathlib import Path
from typing import Protocol

from app.rag.document import KnowledgeDocument


class DocumentLoader(Protocol):
    supported_extensions: frozenset[str]

    def load(self, path: str | Path) -> list[KnowledgeDocument]:
        ...


class UnsupportedDocumentError(ValueError):
    """当前 loader 不支持该文件。"""


def build_document(
    path: str | Path,
    content: str,
    *,
    file_type: str,
    category: str = "policy",
) -> KnowledgeDocument:
    file_path = Path(path)
    title = _extract_title(content) or file_path.stem.replace("_", " ")
    return KnowledgeDocument(
        doc_id=file_path.stem,
        title=title,
        content=content,
        source=file_path.name,
        source_path=str(file_path),
        file_type=file_type,
        category=category,
        metadata={"extension": file_path.suffix.lower()},
    )


def _extract_title(content: str) -> str | None:
    for line in content.splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("#"):
            return text.lstrip("#").strip() or None
        return None
    return None
