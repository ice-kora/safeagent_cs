import os
from pathlib import Path
from typing import Any


class BgeM3Embedder:
    """BAAI/bge-m3 dense embedding provider backed by FlagEmbedding.

    The model is loaded lazily by explicit demo/smoke configuration only. Pytest
    defaults stay on MockEmbedder, so unit tests do not download model weights.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        *,
        device: str = "cpu",
        cache_dir: str | Path | None = None,
        batch_size: int = 16,
        use_fp16: bool | None = None,
    ) -> None:
        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as exc:
            raise RuntimeError(
                "FlagEmbedding is required for SAFEAGENT_RAG_EMBEDDING_PROVIDER=bge_m3. "
                "Install it with: pip install FlagEmbedding"
            ) from exc

        self.model_name = model_name
        self.device = device
        self.cache_dir = str(cache_dir) if cache_dir else None
        self.batch_size = batch_size
        self._last_sparse_vectors: list[Any] | None = None
        if self.cache_dir:
            os.environ.setdefault("HF_HOME", self.cache_dir)
            os.environ.setdefault("TRANSFORMERS_CACHE", self.cache_dir)

        model_kwargs: dict[str, Any] = {
            "use_fp16": (device != "cpu") if use_fp16 is None else use_fp16,
        }
        if device:
            model_kwargs["device"] = device
        if self.cache_dir:
            model_kwargs["cache_dir"] = self.cache_dir

        try:
            self._model = BGEM3FlagModel(model_name, **model_kwargs)
        except TypeError:
            # Older FlagEmbedding builds do not accept cache_dir in the constructor.
            model_kwargs.pop("cache_dir", None)
            self._model = BGEM3FlagModel(model_name, **model_kwargs)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load embedding model {model_name!r} on device {device!r}. "
                "For this demo the target model remains BAAI/bge-m3; if local memory "
                "or network access blocks loading, try a smaller temporary model only "
                "for diagnosis."
            ) from exc

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            encoded = self._model.encode(
                texts,
                batch_size=self.batch_size,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=False,
            )
        except TypeError:
            encoded = self._model.encode(
                texts,
                batch_size=self.batch_size,
                return_dense=True,
            )
        dense_vectors = encoded.get("dense_vecs") if isinstance(encoded, dict) else encoded
        if isinstance(encoded, dict):
            self._last_sparse_vectors = encoded.get("lexical_weights")
        vectors = dense_vectors.tolist() if hasattr(dense_vectors, "tolist") else dense_vectors
        return [[float(value) for value in vector] for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]

    @property
    def last_sparse_vectors(self) -> list[Any] | None:
        """Sparse lexical vectors from the last encode call when available."""
        return self._last_sparse_vectors
