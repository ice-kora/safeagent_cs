import csv
from pathlib import Path

from app.rag.document import KnowledgeDocument
from app.rag.loaders.base import build_document


class CsvLoader:
    supported_extensions = frozenset({".csv"})

    def load(self, path: str | Path) -> list[KnowledgeDocument]:
        rows: list[str] = []
        with Path(path).open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            for row in reader:
                rows.append(" | ".join(cell.strip() for cell in row))
        return [build_document(path, "\n".join(rows), file_type="csv")]
