from typing import Protocol


class Embedder(Protocol):
    """Embedding provider 协议。测试默认使用 MockEmbedder。"""

    model_name: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...
