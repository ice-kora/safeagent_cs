from pathlib import Path

from app.rag.document import KnowledgeDocument
from app.rag.loaders.audio_loader import AudioLoader
from app.rag.loaders.base import DocumentLoader, UnsupportedDocumentError
from app.rag.loaders.csv_loader import CsvLoader
from app.rag.loaders.docx_loader import DocxLoader
from app.rag.loaders.html_loader import HtmlLoader
from app.rag.loaders.image_loader import ImageLoader
from app.rag.loaders.markdown_loader import MarkdownLoader
from app.rag.loaders.pdf_loader import PdfLoader
from app.rag.loaders.text_loader import TextLoader
from app.rag.loaders.xlsx_loader import XlsxLoader


DEFAULT_LOADERS: tuple[DocumentLoader, ...] = (
    TextLoader(),
    MarkdownLoader(),
    HtmlLoader(),
    CsvLoader(),
    PdfLoader(),
    DocxLoader(),
    XlsxLoader(),
    ImageLoader(),
    AudioLoader(),
)


def load_document_file(
    path: str | Path,
    loaders: tuple[DocumentLoader, ...] = DEFAULT_LOADERS,
) -> list[KnowledgeDocument]:
    suffix = Path(path).suffix.lower()
    for loader in loaders:
        if suffix in loader.supported_extensions:
            return loader.load(path)
    raise UnsupportedDocumentError(f"Unsupported knowledge file type: {suffix}")
