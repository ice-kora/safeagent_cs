from pathlib import Path

from app.rag.document import KnowledgeDocument
from app.rag.loaders.base import build_document


class XlsxLoader:
    supported_extensions = frozenset({".xlsx"})

    def load(self, path: str | Path) -> list[KnowledgeDocument]:
        try:
            import openpyxl
        except ImportError as exc:
            raise RuntimeError("openpyxl is required to load XLSX knowledge files") from exc
        workbook = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        rows: list[str] = []
        for sheet in workbook.worksheets:
            rows.append(f"# {sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                values = ["" if cell is None else str(cell) for cell in row]
                rows.append(" | ".join(values))
        return [build_document(path, "\n".join(rows), file_type="xlsx")]
