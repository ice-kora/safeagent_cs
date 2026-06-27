from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class KnowledgeDocument:
    """统一知识文档结构，覆盖 policy corpus 和后续导入文件。"""

    doc_id: str
    title: str
    content: str
    source: str
    source_path: str | None = None
    file_type: str = "text"
    category: str = "policy"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentChunk:
    """统一切片结构，用于 dense / keyword / hybrid 检索。"""

    doc_id: str
    chunk_id: str
    title: str
    text: str
    source: str
    source_path: str | None = None
    file_type: str = "text"
    category: str = "policy"
    metadata: dict[str, Any] = field(default_factory=dict)
