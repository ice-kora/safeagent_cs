import re
from html import unescape
from pathlib import Path

from app.rag.document import KnowledgeDocument
from app.rag.loaders.base import build_document


class HtmlLoader:
    supported_extensions = frozenset({".html", ".htm"})

    def load(self, path: str | Path) -> list[KnowledgeDocument]:
        raw = Path(path).read_text(encoding="utf-8")
        text = re.sub(r"<(script|style).*?</\1>", " ", raw, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", unescape(text)).strip()
        return [build_document(path, text, file_type="html")]
