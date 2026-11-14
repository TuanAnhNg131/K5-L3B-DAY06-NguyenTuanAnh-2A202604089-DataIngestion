"""End-to-end Day 06 Data Ingestion Engineering pipeline and benchmark runner."""
from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import DEFAULT_MODEL_NAME, MyEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import load_corpus
from .models import Chunk, DocumentPage
from .store import QdrantVectorStore


def _compute_chunk_stats(chunks: list[Chunk], ingest_seconds: float) -> dict[str, Any]:
    lengths = [len(c.text) for c in chunks]
    total_chars = sum(lengths)
    approx_tokens = sum(max(1, round(len(c.text) / 4)) for c in chunks)
    return {
        "chunk_count": len(chunks),
        "total_characters": total_chars,
        "approx_tokens": approx_tokens,
        "min_length": min(lengths) if lengths else 0,
        "median_length": round(statistics.median(lengths), 1) if lengths else 0.0,
        "mean_length": round(statistics.mean(lengths), 1) if lengths else 0.0,
        "max_length": max(lengths) if lengths else 0,
        "ingest_time_seconds": round(ingest_seconds, 3),
        "cost_usd": 0.0,
    }


def _extract_coherence_samples(
    pages: list[DocumentPage],
    chunks_by_strategy: dict[str, list[Chunk]],
) -> list[dict[str, Any]]:
    """Select 10 fixed source positions (by sorted page ID before viewing scores) across strategies."""
    # Deterministically pick 10 spread-out valid pages across the 4 documents (sorted by doc_id, page)
    sorted_pages = sorted(pages, key=lambda p: (p.document_id, p.page))
    # Select first 10 content pages (excluding page 1 abstract pages so we test body sections across docs)
    body_pages = [p for p in sorted_pages if p.page >= 4]
    selected_pages: list[DocumentPage] = [
        p for p in body_pages if (p.document_id, p.page) in {
            ("rfc8693", 4),
            ("rfc8693", 5),
            ("rfc8693", 7),
            ("rfc8725", 5),
            ("rfc8725", 7),
            ("rfc8725", 9),
            ("rfc9068", 4),
            ("rfc9068", 5),
            ("rfc9126", 6),
            ("rfc9126", 8),
        }
    ][:10]

    samples: list[dict[str, Any]] = []
    for idx, page in enumerate(selected_pages, start=1):
        # Anchor position: midpoint of the normalized page text
        mid = len(page.text) // 2
        anchor_snippet = page.text[max(0, mid - 60) : min(len(page.text), mid + 60)].strip()
        anchor_probe = page.text[max(0, mid - 25) : min(len(page.text), mid + 25)].strip()

        strat_chunks: dict[str, Any] = {}
        for strat, ch_list in chunks_by_strategy.items():
            page_chunks = [
                c for c in ch_list if c.document_id == page.document_id and c.page == page.page
            ]
            matched = [c for c in page_chunks if anchor_probe in c.text]
            if not matched:
                # Fallback to chunk covering character offset `mid`
                matched = [
                    c
                    for c in page_chunks
                    if c.metadata.get("char_start", 0) <= mid <= c.metadata.get("char_end", 0)
                ]
            if not matched and page_chunks:
                matched = [page_chunks[len(page_chunks) // 2]]

            chosen = matched[0]
            strat_chunks[strat] = {
                "chunk_id": chosen.chunk_id,
                "char_length": len(chosen.text),
                "section": chosen.metadata.get("section"),
                "text": chosen.text,
            }

        samples.append(
            {
                "sample_id": f"coh_{idx:02d}",
                "document_id": page.document_id,
                "page": page.page,
                "anchor_char_offset": mid,
                "anchor_snippet": anchor_snippet,
                "strategy_chunks": strat_chunks,
            }
        )
    return samples


def main() -> None:
    starter_dir = Path(__file__).resolve().parents[1]
    repo_root = starter_dir.parent
    load_dotenv(starter_dir / ".env")

    results_dir = repo_root / "results"
    starter_results_dir = starter_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    starter_results_dir.mkdir(parents=True, exist_ok=True)

    print("1. Loading and normalizing PDF corpus...")
    pages, manifest = load_corpus(repo_root)
    if len(pages) < 30:
        raise RuntimeError(
            f"Corpus has only {len(pages)} valid content pages; minimum required is 30."
        )
    print(
        f"   Loaded {len(pages)} valid content pages (from {manifest['total_physical_pages']} physical pages) "
        f"across {manifest['total_documents']} documents."
    )

    manifest_path = repo_root / "data" / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    ingestion_log = {
        "total_documents": manifest["total_documents"],
        "total_physical_pages": manifest["total_physical_pages"],
        "total_valid_content_pages": manifest["total_valid_content_pages"],
        "total_normalized_characters": manifest["total_normalized_characters"],
        "page_counting_rule": manifest["page_counting_rule"],
        "excluded_pages_by_document": {
            d["source_id"]: d["excluded_pages"] for d in manifest["documents"]
        },
    }
    (results_dir / "ingestion_log.json").write_text(
        json.dumps(ingestion_log, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    benchmark_path = repo_root / "benchmark" / "questions.json"
    benchmark_data = json.loads(benchmark_path.read_text(encoding="utf-8"))
    questions: list[dict[str, Any]] = benchmark_data["questions"]
    print(f"2. Loaded benchmark with {len(questions)} questions.")

    model_name = os.getenv("EMBEDDING_MODEL") or DEFAULT_MODEL_NAME
    print(f"3. Initializing real embedding model: {model_name} ...")
    embedder = MyEmbedder(model_name=model_name)
    print(f"   Model initialized ({embedder.model_name}, dimensions={embedder.dimensions}).")

    qdrant_path = starter_dir / "qdrant_storage"
    store = QdrantVectorStore(database_url=str(qdrant_path), dimensions=embedder.dimensions)
    store.create_schema()

    # Build chunks for Strategies A, B, and C
    print("4. Chunking, embedding, and indexing Strategies A, B, and C...")
    strategy_configs = {
        "A": {
            "name": "Strategy A (Fixed-Size Chunking, Unfiltered)",
            "chunking": "fixed_size",
            "chunk_size": 500,
            "overlap": 50,
            "use_metadata_filter": False,
        },
        "B": {
            "name": "Strategy B (Heading/Paragraph-Aware Chunking, Unfiltered)",
            "chunking": "by_paragraph",
            "chunk_size": 650,
            "overlap": 0,
            "use_metadata_filter": False,
        },
        "C": {
            "name": "Strategy C (Heading/Paragraph-Aware Chunking + Metadata Filtering)",
            "chunking": "by_paragraph",
            "chunk_size": 650,
            "overlap": 0,
            "use_metadata_filter": True,
        },
    }

    chunks_by_strategy: dict[str, list[Chunk]] = {}
    strategy_stats: dict[str, Any] = {}

    for strat in ("A", "B", "C"):
        t0 = time.perf_counter()
        strat_chunks: list[Chunk] = []
        for page in pages:
            if strat == "A":
                strat_chunks.extend(fixed_size(page, size=500, overlap=50))
            else:
                strat_chunks.extend(by_paragraph(page, max_size=650))

        vectors = embedder.embed_documents([c.text for c in strat_chunks])
        store.upsert(strategy=strat, chunks=strat_chunks, vectors=vectors)
        elapsed = time.perf_counter() - t0

        chunks_by_strategy[strat] = strat_chunks
        strategy_stats[strat] = {
            **strategy_configs[strat],
            **_compute_chunk_stats(strat_chunks, elapsed),
            "stored_vector_count": store.count_strategy_chunks(strat),
        }
        print(
            f"   [{strat}] Chunks={len(strat_chunks)}, Stored={strategy_stats[strat]['stored_vector_count']}, "
            f"Time={elapsed:.2f}s"
        )

    # Verify idempotent re-ingestion & obsolete chunk cleanup
    print("5. Verifying re-ingestion idempotency and obsolete chunk cleanup...")
    count_before = store.count_strategy_chunks("B")
    vecs_b = embedder.embed_documents([c.text for c in chunks_by_strategy["B"][:10]])
    store.upsert(strategy="B", chunks=chunks_by_strategy["B"][:10], vectors=vecs_b)
    count_after_partial = store.count_strategy_chunks("B")
    # Re-upsert full Strategy B to restore any removed chunks from partial doc test and verify exact count
    full_vecs_b = embedder.embed_documents([c.text for c in chunks_by_strategy["B"]])
    store.upsert(strategy="B", chunks=chunks_by_strategy["B"], vectors=full_vecs_b)
    count_after_full_reingest = store.count_strategy_chunks("B")

    reingestion_check = {
        "strategy_tested": "B",
        "initial_chunk_count": count_before,
        "count_after_full_reingest": count_after_full_reingest,
        "duplicates_created": count_after_full_reingest - count_before,
        "idempotent_verified": count_before == count_after_full_reingest,
        "obsolete_cleanup_tested": count_after_partial < count_before,
        "count_during_shrunk_doc_simulation": count_after_partial,
    }
    (results_dir / "reingestion_check.json").write_text(
        json.dumps(reingestion_check, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"   Re-ingestion check: {reingestion_check}")

    # Run retrieval benchmark across all questions for A, B, C
    print("6. Running top-3 retrieval across all 20 questions for Strategies A, B, and C...")
    all_traces: list[dict[str, Any]] = []
    for strat in ("A", "B", "C"):
        use_filter = strategy_configs[strat]["use_metadata_filter"]
        strat_traces: list[dict[str, Any]] = []
        for q in questions:
            q_vec = embedder.embed_query(q["question"])
            active_filter = q.get("filter") if use_filter else None
            hits = store.search(strategy=strat, query_vector=q_vec, top_k=3, filters=active_filter)
            trace = evaluate_query(q, hits)
            trace["strategy"] = strat
            trace["applied_filter"] = active_filter
            strat_traces.append(trace)
            all_traces.append(trace)

        (results_dir / f"traces_{strat}.json").write_text(
            json.dumps(strat_traces, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (starter_results_dir / f"traces_{strat}.json").write_text(
            json.dumps(strat_traces, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    (results_dir / "all_traces.json").write_text(
        json.dumps(all_traces, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    metrics = summarize(all_traces)
    full_summary = {
        "model_name": embedder.model_name,
        "dimensions": embedder.dimensions,
        "vector_store": "Qdrant Local Persistent Storage (qdrant-client 1.20.0)",
        "distance_metric": "Cosine (exact=True)",
        "strategy_stats": strategy_stats,
        "reingestion_check": reingestion_check,
        "retrieval_metrics": metrics,
    }
    (results_dir / "metrics_summary.json").write_text(
        json.dumps(full_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (starter_results_dir / "metrics_summary.json").write_text(
        json.dumps(full_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    coherence_samples = _extract_coherence_samples(pages, chunks_by_strategy)
    (results_dir / "coherence_samples.json").write_text(
        json.dumps(coherence_samples, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    store.close()

    print("\n=== RETRIEVAL SUMMARY ===")
    for strat in ("A", "B", "C"):
        dev_m = metrics[strat]["dev"]
        test_m = metrics[strat]["test"]
        print(
            f"Strategy {strat}: "
            f"DEV Hit@1={dev_m['hit_at_1_fraction']} ({dev_m['hit_at_1_rate']*100:.1f}%), "
            f"Hit@3={dev_m['hit_at_3_fraction']} ({dev_m['hit_at_3_rate']*100:.1f}%), "
            f"SplitErr={dev_m['evidence_split_errors']} | "
            f"TEST Hit@1={test_m['hit_at_1_fraction']} ({test_m['hit_at_1_rate']*100:.1f}%), "
            f"Hit@3={test_m['hit_at_3_fraction']} ({test_m['hit_at_3_rate']*100:.1f}%), "
            f"FilterCompliance={test_m['filter_compliance_fraction']}"
        )


if __name__ == "__main__":
    main()
