"""Real SentenceTransformers embedding adapter (no mock fallback)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

_LOCAL_SCRATCH_HF_CACHE = Path(
    r"C:\Users\Tuan Anh\.gemini\antigravity\brain\bc0d734a-0f51-4f0c-9ad8-a358f2c409b0\scratch\hf_cache"
)
if "HF_HOME" not in os.environ and _LOCAL_SCRATCH_HF_CACHE.exists():
    os.environ["HF_HOME"] = str(_LOCAL_SCRATCH_HF_CACHE)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from sentence_transformers import SentenceTransformer  # noqa: E402

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """Real SentenceTransformers local embedding provider.

    Raises an explicit runtime error if the model cannot be loaded or fails;
    never falls back to random or mock vectors.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        if not model_name or not model_name.strip():
            raise ValueError("model_name must be a non-empty string")
        self.model_name = model_name.strip()

        local_only = os.environ.get("HF_HUB_OFFLINE") == "1"
        self._model = SentenceTransformer(self.model_name, local_files_only=local_only)
        dim = self._model.get_embedding_dimension()
        if not dim or dim <= 0:
            raise RuntimeError(f"Invalid embedding dimension returned by {self.model_name}: {dim}")
        self.dimensions: int = int(dim)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        embeddings = self._model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return [vec.astype(float).tolist() for vec in embeddings]

    def embed_query(self, question: str) -> list[float]:
        if not question or not question.strip():
            raise ValueError("Query question must be non-empty")
        embedding = self._model.encode(
            [question.strip()],
            batch_size=1,
            show_progress_bar=False,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )[0]
        return embedding.astype(float).tolist()
