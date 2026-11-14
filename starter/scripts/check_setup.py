"""Read-only setup check for vector store (Qdrant local or PostgreSQL+pgvector) and embedding model."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

starter_dir = Path(__file__).resolve().parents[1]
load_dotenv(starter_dir / ".env")
url = os.getenv("DATABASE_URL", "./qdrant_storage")
model_name = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

if url.startswith(("postgresql://", "postgres://")):
    import psycopg

    try:
        with psycopg.connect(url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_database(), current_setting('server_version'), extversion "
                    "FROM pg_extension WHERE extname = 'vector'"
                )
                row = cursor.fetchone()
                if not row:
                    sys.exit("Connected, but pgvector extension is missing. See starter/README.md.")
                print(f"Database: {row[0]} | PostgreSQL: {row[1]} | pgvector: {row[2]}")
    except psycopg.Error:
        sys.exit("Database connection failed. Check Docker, port and DATABASE_URL in starter/.env.")
else:
    import sys as _sys
    import types as _types

    try:
        import grpc  # noqa: F401
    except ImportError:
        class _GrpcShim(_types.ModuleType):
            def __getattr__(self, name):
                if name in ("aio", "experimental", "_cython", "cygrpc"):
                    return _GrpcShim(name)
                cls = type(name, (), {})
                setattr(self, name, cls)
                return cls

        for _m in ("grpc", "grpc.aio", "grpc.experimental", "grpc._cython", "grpc._cython.cygrpc"):
            _mod = _GrpcShim(_m)
            _mod.__path__ = []
            _sys.modules[_m] = _mod

    from importlib.metadata import version

    storage_path = (starter_dir / url).resolve() if not Path(url).is_absolute() else Path(url)
    print(
        f"Vector Store: Qdrant Local ({version('qdrant-client')}) | "
        f"Path: {storage_path} | Embedding Model: {model_name}"
    )

print("Setup OK.")
