"""Evaluate retrieved evidence and preserve per-query traces."""
from __future__ import annotations

import re
from typing import Any


def _collapse_ws(text: str) -> str:
    """Collapse whitespace so line wraps do not cause false negatives when checking full evidence containment."""
    return re.sub(r"\s+", " ", text or "").strip()


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Check source/page and full gold evidence containment; preserve detailed per-hit trace.

    A single chunk is an Evidence Hit if and only if:
    1. It comes from the gold document (`document_id == gold_source_id`) and gold page (`page == gold_page`), AND
    2. Its text contains the full `evidence_quote` (normalized for whitespace).
    If a chunk on the gold page only contains part of the `evidence_quote` because chunking split the quote,
    it is flagged as `partial_evidence_split=True` (and NOT counted as a single-chunk hit).
    """
    gold_doc = question["gold_source_id"]
    gold_page = int(question["gold_page"])
    gold_quote_norm = _collapse_ws(question["evidence_quote"])

    # Use 45-char prefix and suffix of the evidence quote to detect when a quote was split across chunks
    quote_prefix = gold_quote_norm[: min(45, len(gold_quote_norm))]
    quote_suffix = gold_quote_norm[max(0, len(gold_quote_norm) - 45) :]

    req_filter: dict[str, Any] | None = question.get("filter")
    evaluated_hits: list[dict[str, Any]] = []

    for idx, hit in enumerate(hits, start=1):
        hit_doc = hit.get("document_id") or hit.get("metadata", {}).get("document_id")
        hit_page = int(hit.get("page") or hit.get("metadata", {}).get("page") or -1)
        hit_text_norm = _collapse_ws(hit.get("text", ""))

        same_source_page = (hit_doc == gold_doc) and (hit_page == gold_page)
        full_evidence_match = same_source_page and (gold_quote_norm in hit_text_norm)
        partial_split = (
            same_source_page
            and not full_evidence_match
            and ((quote_prefix in hit_text_norm) or (quote_suffix in hit_text_norm))
        )

        filter_compliant = True
        if req_filter:
            meta = hit.get("metadata", {})
            for fk, fv in req_filter.items():
                if meta.get(fk) != fv:
                    filter_compliant = False
                    break

        evaluated_hits.append(
            {
                "rank": idx,
                "chunk_id": hit.get("chunk_id"),
                "score": hit.get("score"),
                "document_id": hit_doc,
                "source": hit.get("source") or hit.get("metadata", {}).get("source"),
                "page": hit_page,
                "metadata": hit.get("metadata", {}),
                "text": hit.get("text", ""),
                "same_gold_source_and_page": same_source_page,
                "is_evidence_hit": full_evidence_match,
                "partial_evidence_split": partial_split,
                "filter_compliant": filter_compliant,
            }
        )

    hit_at_1 = bool(evaluated_hits and evaluated_hits[0]["is_evidence_hit"])
    hit_at_3 = any(h["is_evidence_hit"] for h in evaluated_hits[:3])

    # Diagnostic only (does not replace strict single-chunk Hit@3): check if combining top-3 gold-page chunks reconstructs the quote
    gold_page_texts = " ".join(
        _collapse_ws(h["text"]) for h in evaluated_hits[:3] if h["same_gold_source_and_page"]
    )
    multi_chunk_combined_hit = bool(
        not hit_at_3
        and (quote_prefix in gold_page_texts)
        and (quote_suffix in gold_page_texts)
    )
    any_split_error = any(h["partial_evidence_split"] for h in evaluated_hits[:3]) and not hit_at_3

    top3_all_filter_compliant: bool | None = None
    if req_filter:
        top3_all_filter_compliant = bool(
            evaluated_hits and all(h["filter_compliant"] for h in evaluated_hits[:3])
        )

    return {
        "question_id": question["id"],
        "split": question["split"],
        "question_type": question.get("type", "general"),
        "question": question["question"],
        "expected_answer": question.get("expected_answer", ""),
        "gold_source_id": gold_doc,
        "gold_page": gold_page,
        "evidence_quote": question["evidence_quote"],
        "requested_filter": req_filter,
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
        "evidence_split_error": any_split_error,
        "multi_chunk_combined_hit": multi_chunk_combined_hit,
        "top3_filter_compliant": top3_all_filter_compliant,
        "top_k_hits": evaluated_hits[:3],
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 and Evidence Hit@3 (with numerator/denominator) by strategy and dev/test split."""
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for tr in traces:
        strat = tr.get("strategy", "unknown")
        split = tr.get("split", "unknown")
        grouped.setdefault(strat, {}).setdefault(split, []).append(tr)
        grouped.setdefault(strat, {}).setdefault("all", []).append(tr)

    summary: dict[str, Any] = {}
    for strat, splits in grouped.items():
        summary[strat] = {}
        for split_name, items in splits.items():
            total = len(items)
            h1 = sum(1 for x in items if x["hit_at_1"])
            h3 = sum(1 for x in items if x["hit_at_3"])
            split_errs = sum(1 for x in items if x.get("evidence_split_error"))
            filter_qs = [x for x in items if x.get("requested_filter")]
            filter_ok = sum(1 for x in filter_qs if x.get("top3_filter_compliant") is True)
            summary[strat][split_name] = {
                "total_questions": total,
                "hit_at_1_count": h1,
                "hit_at_1_fraction": f"{h1}/{total}",
                "hit_at_1_rate": round(h1 / total, 4) if total else 0.0,
                "hit_at_3_count": h3,
                "hit_at_3_fraction": f"{h3}/{total}",
                "hit_at_3_rate": round(h3 / total, 4) if total else 0.0,
                "evidence_split_errors": split_errs,
                "filter_questions_count": len(filter_qs),
                "filter_compliant_count": filter_ok,
                "filter_compliance_fraction": (
                    f"{filter_ok}/{len(filter_qs)}" if filter_qs else "N/A"
                ),
            }
    return summary
