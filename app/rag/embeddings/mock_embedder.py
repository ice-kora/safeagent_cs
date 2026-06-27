import hashlib
import math


class MockEmbedder:
    """确定性本地 embedding，不联网，用于测试和 dev fallback。"""

    model_name = "mock-hash-embedding"

    def __init__(self, dimensions: int = 16) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = digest[0] % self.dimensions
            vector[index] += 1.0 + digest[1] / 255.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


def _tokens(text: str) -> list[str]:
    normalized = text.lower()
    ascii_tokens = []
    current = []
    for char in normalized:
        if char.isascii() and char.isalnum():
            current.append(char)
        else:
            if len(current) >= 2:
                ascii_tokens.append("".join(current))
            current = []
    if len(current) >= 2:
        ascii_tokens.append("".join(current))
    cjk_tokens = [char for char in normalized if "\u4e00" <= char <= "\u9fff"]
    return ascii_tokens + cjk_tokens
