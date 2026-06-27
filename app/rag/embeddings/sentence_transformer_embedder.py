from pathlib import Path


class SentenceTransformersEmbedder:
    """sentence-transformers embedding provider.

    该类只在显式配置时加载模型；pytest 默认不会实例化它，因此不会联网
    下载模型。
    """

    def __init__(
        self,
        model_name: str,
        device: str = "cpu",
        cache_dir: str | Path | None = None,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence_transformers is required for real RAG embeddings"
            ) from exc
        self.model_name = model_name
        self._model = SentenceTransformer(
            model_name,
            device=device,
            cache_folder=str(cache_dir) if cache_dir else None,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [list(vector) for vector in vectors]
