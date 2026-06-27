from pathlib import Path

from app.rag.document import KnowledgeDocument


class AudioLoader:
    supported_extensions = frozenset({".mp3", ".wav", ".m4a"})

    def load(self, path: str | Path) -> list[KnowledgeDocument]:
        raise RuntimeError("Audio ASR ingestion is intentionally disabled in v1.0")
