"""Persistent Vector Store implementation using Qdrant Local on-disk storage with Cosine distance and metadata filtering."""
from __future__ import annotations

import sys
import types
import uuid
from pathlib import Path
from typing import Any

try:
    import grpc  # noqa: F401
except ImportError:
    # QdrantClient(path=...) uses pure-Python/NumPy local storage and does not invoke gRPC.
    # Provide an import-time shim if Windows Smart App Control blocks grpcio's cygrpc.pyd.
    class _GrpcImportShim(types.ModuleType):
        def __getattr__(self, name: str) -> Any:
            if name in ("aio", "experimental", "_cython", "cygrpc"):
                sub = _GrpcImportShim(name)
                setattr(self, name, sub)
                return sub
            cls = type(name, (), {})
            setattr(self, name, cls)
            return cls

    for _mod_name in ("grpc", "grpc.aio", "grpc.experimental", "grpc._cython", "grpc._cython.cygrpc"):
        _mod = _GrpcImportShim(_mod_name)
        _mod.__path__ = []  # type: ignore[attr-defined]
        sys.modules[_mod_name] = _mod

from qdrant_client import QdrantClient, models

from .models import Chunk

PERMITTED_FILTER_FIELDS = {"year", "category", "section", "document_id", "source", "page", "rfc_number"}


class QdrantVectorStore:
    """Persistent on-disk Qdrant vector store supporting cosine similarity, metadata filtering, and idempotent upsert."""

    COLLECTION_NAME = "day06_rag_chunks"

    def __init__(self, database_url: str, dimensions: int) -> None:
        if dimensions <= 0:
            raise ValueError(f"dimensions must be positive, got {dimensions}")
        self.dimensions = int(dimensions)
        self.database_url = database_url

        # Interpret database_url / path as persistent local storage directory on disk
        if database_url.startswith(("postgresql://", "postgres://")):
            storage_dir = Path(__file__).resolve().parents[1] / "qdrant_storage"
        else:
            storage_dir = Path(database_url)
        storage_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path = str(storage_dir.resolve())
        self.client = QdrantClient(path=self.storage_path)

    def create_schema(self) -> None:
        """Create persistent Qdrant collection configured with Cosine distance if it does not exist."""
        existing = [c.name for c in self.client.get_collections().collections]
        if self.COLLECTION_NAME in existing:
            info = self.client.get_collection(self.COLLECTION_NAME)
            vec_params = info.config.params.vectors
            existing_dim = getattr(vec_params, "size", None)
            if existing_dim and existing_dim != self.dimensions:
                raise ValueError(
                    f"Existing collection dimension ({existing_dim}) != model dimension ({self.dimensions})"
                )
            return

        self.client.create_collection(
            collection_name=self.COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=self.dimensions,
                distance=models.Distance.COSINE,
            ),
        )

    @staticmethod
    def _point_id(strategy: str, chunk_id: str) -> str:
        """Generate a deterministic UUID5 from (strategy, chunk_id) so re-ingestion never creates duplicates."""
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{strategy}::{chunk_id}"))

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Validate lengths/dimensions, remove obsolete chunks for updated documents, and upsert deterministically."""
        if len(chunks) != len(vectors):
            raise ValueError(f"Chunk count ({len(chunks)}) != vector count ({len(vectors)})")
        if not chunks:
            return

        for idx, vec in enumerate(vectors):
            if len(vec) != self.dimensions:
                raise ValueError(
                    f"Vector at index {idx} has dimension {len(vec)}, expected {self.dimensions}"
                )

        # Group incoming chunk_ids by document_id to clean up obsolete chunks when a document changes
        incoming_by_doc: dict[str, set[str]] = {}
        for ch in chunks:
            incoming_by_doc.setdefault(ch.document_id, set()).add(ch.chunk_id)

        for doc_id, valid_chunk_ids in incoming_by_doc.items():
            existing_points, _ = self.client.scroll(
                collection_name=self.COLLECTION_NAME,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(key="strategy", match=models.MatchValue(value=strategy)),
                        models.FieldCondition(key="document_id", match=models.MatchValue(value=doc_id)),
                    ]
                ),
                limit=10000,
                with_payload=True,
                with_vectors=False,
            )
            obsolete_ids = [
                pt.id
                for pt in existing_points
                if pt.payload and pt.payload.get("chunk_id") not in valid_chunk_ids
            ]
            if obsolete_ids:
                self.client.delete(
                    collection_name=self.COLLECTION_NAME,
                    points_selector=models.PointIdsList(points=obsolete_ids),
                )

        points: list[models.PointStruct] = []
        for ch, vec in zip(chunks, vectors):
            payload = {
                **ch.metadata,
                "strategy": strategy,
                "chunk_id": ch.chunk_id,
                "document_id": ch.document_id,
                "source": ch.source,
                "page": int(ch.page),
                "text": ch.text,
            }
            points.append(
                models.PointStruct(
                    id=self._point_id(strategy, ch.chunk_id),
                    vector=vec,
                    payload=payload,
                )
            )

        self.client.upsert(collection_name=self.COLLECTION_NAME, points=points)

    def count_strategy_chunks(self, strategy: str) -> int:
        """Return total number of stored chunks for a given strategy."""
        res = self.client.count(
            collection_name=self.COLLECTION_NAME,
            count_filter=models.Filter(
                must=[models.FieldCondition(key="strategy", match=models.MatchValue(value=strategy))]
            ),
            exact=True,
        )
        return int(res.count)

    def search(
        self,
        strategy: str,
        query_vector: list[float],
        top_k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Filter permitted metadata in Qdrant, rank by exact cosine similarity, and return top-k."""
        if len(query_vector) != self.dimensions:
            raise ValueError(
                f"Query vector dimension ({len(query_vector)}) != store dimension ({self.dimensions})"
            )

        must_conditions: list[models.Condition] = [
            models.FieldCondition(key="strategy", match=models.MatchValue(value=strategy))
        ]
        if filters:
            for key, val in filters.items():
                if key not in PERMITTED_FILTER_FIELDS:
                    raise ValueError(f"Unsupported metadata filter field: {key}")
                must_conditions.append(
                    models.FieldCondition(key=key, match=models.MatchValue(value=val))
                )

        response = self.client.query_points(
            collection_name=self.COLLECTION_NAME,
            query=query_vector,
            query_filter=models.Filter(must=must_conditions),
            limit=top_k,
            with_payload=True,
            with_vectors=False,
            search_params=models.SearchParams(exact=True),
        )

        results: list[dict[str, Any]] = []
        for rank, scored_pt in enumerate(response.points, start=1):
            payload = dict(scored_pt.payload or {})
            chunk_id = payload.pop("chunk_id", str(scored_pt.id))
            text = payload.pop("text", "")
            results.append(
                {
                    "rank": rank,
                    "chunk_id": chunk_id,
                    "score": round(float(scored_pt.score), 6),
                    "text": text,
                    "document_id": payload.get("document_id"),
                    "source": payload.get("source"),
                    "page": payload.get("page"),
                    "metadata": payload,
                }
            )
        return results

    def close(self) -> None:
        self.client.close()


# Keep PgVectorStore alias for starter template compatibility
PgVectorStore = QdrantVectorStore
