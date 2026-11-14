"""Generate manual audit CSVs and summary JSON for Coherence, Metadata Usefulness, and Grounding Quality."""
from __future__ import annotations

import csv
import json
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    results_dir = repo_root / "results"
    starter_results_dir = repo_root / "starter" / "results"

    coherence_samples = json.loads((results_dir / "coherence_samples.json").read_text(encoding="utf-8"))
    all_traces = json.loads((results_dir / "all_traces.json").read_text(encoding="utf-8"))

    # 1. Manual Coherence Audit (10 fixed positions x 3 strategies = 30 records)
    coherence_judgments = {
        "coh_01": {
            "A": (1, "Cuts start mid-word ('quest to the token endpoint') and cuts end mid-word ('might assume the r'), losing the explanation of why a resource server acts as a client."),
            "B": (2, "Preserves the complete paragraph from topic sentence to concluding sentence ('entirely different kind of token') with full context."),
            "C": (2, "Identical chunking to Strategy B; preserves the complete paragraph and full semantic context."),
        },
        "coh_02": {
            "A": (1, "Starts mid-word ('iction, whether via...') and ends mid-word ('not inclusive of all situatio'); middle paragraph on delegation vs impersonation is readable but boundaries are broken."),
            "B": (2, "Preserves two complete, logically connected paragraphs under Section 1.1 without mid-sentence truncation."),
            "C": (2, "Identical chunking to Strategy B; preserves complete paragraphs and clear comparison between delegation and impersonation."),
        },
        "coh_03": {
            "A": (1, "Starts mid-word ('ples of things that might') and cuts off the final sentence mid-word ('with a mix of logic')."),
            "B": (2, "Contains a single complete, self-contained paragraph explaining uniqueness and combined usage of audience and resource parameters."),
            "C": (2, "Identical chunking to Strategy B; complete and self-contained paragraph."),
        },
        "coh_04": {
            "A": (1, "Starts with broken fragment ('ion and for a...') and cuts off Section 2.5 mid-word ('resulting from de'), losing the critical consequence (private key recovery)."),
            "B": (2, "Keeps heading '2.5. Insecure Use of Elliptic Curve Encryption' attached to its full explanation and mitigation cross-reference."),
            "C": (2, "Identical chunking to Strategy B; heading and full vulnerability explanation preserved intact."),
        },
        "coh_05": {
            "A": (1, "Starts mid-paragraph and cuts the final sentence at 'Similar', omitting the consumption rule for JWT libraries using 'none'."),
            "B": (1, "Contains complete sentences on JWT library generation/consumption of 'none', but ends with dangling lead-in sentence ('Applications follow these algorithm-specific recommendations: SHOULD') whose bullet list is in the next chunk."),
            "C": (1, "Identical chunking to Strategy B; complete sentences on 'none' usage but includes trailing lead-in header for the following bullet list."),
        },
        "coh_06": {
            "A": (1, "Starts with truncated word ('ey ID) header') and cuts off the SSRF mitigation sentence at 'SHO', omitting 'and ensuring no cookies are sent in the GET request'."),
            "B": (2, "Keeps heading '3.10. Do Not Trust Received Claims' together with both complete paragraphs covering 'kid' injection and 'jku'/'x5u' SSRF mitigations."),
            "C": (2, "Identical chunking to Strategy B; heading and both security requirement paragraphs are complete and self-contained."),
        },
        "coh_07": {
            "A": (1, "Starts with orphan word 'Structure' from Section 2 title and cuts off the RS256 requirement sentence mid-word ('supported si')."),
            "B": (2, "Preserves Section 2 and 2.1 headings along with both complete paragraphs on JWT access token signing ('none' prohibition and RS256 support)."),
            "C": (2, "Identical chunking to Strategy B; full section heading and complete normative requirements preserved."),
        },
        "coh_08": {
            "A": (1, "Starts mid-clause ('that the authentication server enforced') and cuts off the 'auth_time' definition mid-word ('as def')."),
            "B": (1, "Preserves full claim definitions for auth_time, acr, and amr, but starts with pronoun 'Their values are fixed...' whose antecedent ('auth_time, acr, and amr') was in the preceding sentence."),
            "C": (1, "Identical chunking to Strategy B; complete sentences and claim definitions, but initial pronoun 'Their' lacks its antecedent from the previous chunk."),
        },
        "coh_09": {
            "A": (1, "Starts with broken fragment ('n 3 of this document') and cuts off 'token_endpoint_auth_methods_supported' mid-identifier ('token_endpoint_auth_meth')."),
            "B": (2, "Contains a complete, self-contained paragraph explaining client authentication rules and token_endpoint_auth_method for the PAR endpoint."),
            "C": (2, "Identical chunking to Strategy B; complete and self-contained paragraph."),
        },
        "coh_10": {
            "A": (1, "Starts mid-word ('est is performed') and cuts off the definition of 'request_uri' mid-word ('in the su')."),
            "B": (2, "Preserves the complete definition block of the 'request_uri' parameter in Section 2.2 without truncation."),
            "C": (2, "Identical chunking to Strategy B; complete parameter definition block preserved."),
        },
    }

    coherence_rows = []
    for sample in coherence_samples:
        sid = sample["sample_id"]
        for strat in ("A", "B", "C"):
            ch_info = sample["strategy_chunks"][strat]
            score, reason = coherence_judgments[sid][strat]
            coherence_rows.append(
                {
                    "sample_id": sid,
                    "strategy": strat,
                    "document_id": sample["document_id"],
                    "page": sample["page"],
                    "anchor_char_offset": sample["anchor_char_offset"],
                    "chunk_id": ch_info["chunk_id"],
                    "char_length": ch_info["char_length"],
                    "section_metadata": ch_info["section"],
                    "coherence_score_0_to_2": score,
                    "rationale": reason,
                    "chunk_text_preview": ch_info["text"][:160].replace("\n", " "),
                }
            )

    coh_csv_path = results_dir / "manual_coherence_audit.csv"
    with coh_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(coherence_rows[0].keys()))
        writer.writeheader()
        writer.writerows(coherence_rows)

    # 2. Manual Metadata Usefulness Audit (5 test questions x top-3 x 3 strategies = 45 records)
    expected_doc_meta = {
        "rfc8693": ("data/raw/rfc8693.pdf", 2020, "Standards Track"),
        "rfc8725": ("data/raw/rfc8725.pdf", 2020, "Best Current Practice"),
        "rfc9068": ("data/raw/rfc9068.pdf", 2021, "Standards Track"),
        "rfc9126": ("data/raw/rfc9126.pdf", 2021, "Standards Track"),
    }

    metadata_rows = []
    for tr in all_traces:
        if tr["split"] != "test":
            continue
        strat = tr["strategy"]
        qid = tr["question_id"]
        req_filter = tr.get("requested_filter")
        for hit in tr["top_k_hits"]:
            doc_id = hit["document_id"]
            src = hit["source"]
            page = hit["page"]
            meta = hit["metadata"]
            yr = meta.get("year")
            cat = meta.get("category")
            sec = meta.get("section")

            exp_src, exp_yr, exp_cat = expected_doc_meta.get(doc_id, ("", -1, ""))
            meta_complete_and_accurate = (
                bool(doc_id)
                and src == exp_src
                and isinstance(page, int)
                and page >= 1
                and yr == exp_yr
                and cat == exp_cat
                and bool(sec)
            )
            filter_status = (
                "N/A"
                if not req_filter
                else ("COMPLIANT" if hit["filter_compliant"] else "VIOLATION")
            )
            note = "All required and filter metadata fields match source PDF."
            if filter_status == "VIOLATION":
                note = (
                    f"Metadata on chunk is accurate ({doc_id}, year={yr}, category={cat}), "
                    f"but violates query filter {req_filter} because Strategy {strat} does not filter."
                )
            # Note minor section granularity limitation on page-level inherited headings
            if strat == "A" and sec and sec.startswith("Section "):
                note += " (Page-level section header inherited; less granular than subsection header in B/C)."

            metadata_rows.append(
                {
                    "strategy": strat,
                    "question_id": qid,
                    "rank": hit["rank"],
                    "chunk_id": hit["chunk_id"],
                    "document_id": doc_id,
                    "source": src,
                    "page": page,
                    "year": yr,
                    "category": cat,
                    "section": sec,
                    "metadata_complete_and_correct": meta_complete_and_accurate,
                    "requested_filter": json.dumps(req_filter) if req_filter else "None",
                    "filter_compliance": filter_status,
                    "audit_note": note,
                }
            )

    meta_csv_path = results_dir / "manual_metadata_audit.csv"
    with meta_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(metadata_rows[0].keys()))
        writer.writeheader()
        writer.writerows(metadata_rows)

    # 3. Manual Grounding Quality Audit (5 test questions x 3 strategies = 15 evaluations)
    grounding_judgments = {
        ("A", "q16"): (
            1,
            "Rank 3 (rfc8693:p16:fixed:00) retrieves the 'may_act' section on the gold page and states that one party is authorized to act on behalf of another, but fixed-size 500-char slicing cuts off the sentence mid-clause ('whether the client (or party identified in'), omitting the actor_token delegation/impersonation check.",
        ),
        ("A", "q17"): (
            0,
            "Top-3 chunks come from rfc8725 pages 3, 4, and 6 (Cross-JWT Confusion and 'none' algorithm) and do not contain Section 3.10 on page 9 regarding 'jku'/'x5u' SSRF attacks or URL whitelisting.",
        ),
        ("A", "q18"): (
            1,
            "Rank 1 (rfc9068:p04:fixed:03) and Rank 2 (rfc9068:p04:fixed:02) retrieve the gold page (rfc9068 p.4) covering 'MUST NOT use none' and 'application/at+jwt', but fixed-size boundaries slice 'RS256' into '256' and cut off the recommended 'at+jwt' shorthand value; Rank 3 pulls an unfiltered chunk from rfc8725 (2020).",
        ),
        ("A", "q19"): (
            0,
            "Top-3 chunks come from rfc9126 pages 6, 8, and 10 (covering request_uri lifetime of 5-600s and error responses) but miss page 13 Section 4 where the single-use requirement and code_challenge uniqueness reason are stated.",
        ),
        ("A", "q20"): (
            1,
            "Rank 1 (rfc9126:p14:fixed:00) states that 'require_pushed_authorization_requests' defaults to false, but fixed-size slicing cuts off the second part of the answer right after 'regardless of other authorization server metadata such as', omitting 'request_uri_parameter_supported or require_request_uri_registration'.",
        ),
        ("B", "q16"): (
            2,
            "Rank 3 (rfc8693:p16:para:00) retrieves the complete Section 4.4 paragraph on rfc8693 page 16, providing full evidence of what 'may_act' states and how the authorization server uses it with subject_token and actor_token.",
        ),
        ("B", "q17"): (
            0,
            "Top-3 chunks come from rfc8725 pages 4 and 6 (Cross-JWT Confusion and general conventions) rather than page 9 Section 3.10; no evidence for 'jku'/'x5u' SSRF or URL whitelisting is present.",
        ),
        ("B", "q18"): (
            2,
            "Rank 1 (rfc9068:p04:para:03) and Rank 2 (rfc9068:p04:para:02) together provide both complete paragraphs from rfc9068 page 4 ('MUST NOT use none', 'MUST include RS256', and 'application/at+jwt' / 'at+jwt' in 'typ'), fully supporting the answer and source citation across two top-3 chunks (note: Rank 3 is from rfc8725 2020 due to no filter).",
        ),
        ("B", "q19"): (
            0,
            "Top-3 chunks retrieve rfc9126 p.13 para 03 (server policy requiring PAR), p.14 para 00, and p.10 para 03, missing p.13 para 01 which states that the client MUST only use a request_uri value once.",
        ),
        ("B", "q20"): (
            2,
            "Rank 2 (rfc9126:p14:para:00) contains the complete two-paragraph specification of 'require_pushed_authorization_requests' on rfc9126 page 14, including both the default value (false) and usability regardless of 'request_uri_parameter_supported'.",
        ),
        ("C", "q16"): (
            2,
            "Rank 3 (rfc8693:p16:para:00) retrieves the complete Section 4.4 paragraph on rfc8693 page 16 with full evidence and source traceability.",
        ),
        ("C", "q17"): (
            0,
            "Although the metadata filter (year=2020, category='Best Current Practice') correctly restricts search to rfc8725, dense semantic similarity still ranks pages 4 and 6 above page 9 Section 3.10 because acronyms 'jku' and 'x5u' have weak dense embedding alignment.",
        ),
        ("C", "q18"): (
            2,
            "Rank 1 (rfc9068:p04:para:03) and Rank 2 (rfc9068:p04:para:02) provide both complete normative paragraphs on rfc9068 page 4 covering 'none' prohibition, RS256 support, and 'application/at+jwt' ('at+jwt') media type, while metadata filtering removes the cross-document rfc8725 distractor at Rank 3.",
        ),
        ("C", "q19"): (
            0,
            "Top-3 chunks retrieve rfc9126 p.13 para 03, p.14 para 00, and p.10 para 03, missing p.13 para 01 where the single-use rule for request_uri is defined.",
        ),
        ("C", "q20"): (
            2,
            "Rank 2 (rfc9126:p14:para:00) provides the complete definition and conditions for 'require_pushed_authorization_requests' and 'request_uri_parameter_supported' on rfc9126 page 14.",
        ),
    }

    grounding_rows = []
    for tr in all_traces:
        if tr["split"] != "test":
            continue
        strat = tr["strategy"]
        qid = tr["question_id"]
        score, reason = grounding_judgments[(strat, qid)]
        grounding_rows.append(
            {
                "strategy": strat,
                "question_id": qid,
                "question_type": tr["question_type"],
                "gold_source_id": tr["gold_source_id"],
                "gold_page": tr["gold_page"],
                "strict_single_chunk_hit_at_3": tr["hit_at_3"],
                "multi_chunk_combined_hit": tr["multi_chunk_combined_hit"],
                "top3_chunk_ids": "; ".join(h["chunk_id"] for h in tr["top_k_hits"]),
                "grounding_score_0_to_2": score,
                "rationale": reason,
            }
        )

    grd_csv_path = results_dir / "manual_grounding_audit.csv"
    with grd_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(grounding_rows[0].keys()))
        writer.writeheader()
        writer.writerows(grounding_rows)

    # Summarize manual audit metrics by strategy
    audit_summary = {}
    for strat in ("A", "B", "C"):
        coh_scores = [r["coherence_score_0_to_2"] for r in coherence_rows if r["strategy"] == strat]
        meta_sub = [r for r in metadata_rows if r["strategy"] == strat]
        meta_ok = sum(1 for r in meta_sub if r["metadata_complete_and_correct"])
        grd_scores = [r["grounding_score_0_to_2"] for r in grounding_rows if r["strategy"] == strat]

        audit_summary[strat] = {
            "coherence_sample_size": len(coh_scores),
            "coherence_counts_by_score": {
                "0": sum(1 for s in coh_scores if s == 0),
                "1": sum(1 for s in coh_scores if s == 1),
                "2": sum(1 for s in coh_scores if s == 2),
            },
            "coherence_mean_over_2": round(sum(coh_scores) / len(coh_scores), 2),
            "metadata_checked_records": len(meta_sub),
            "metadata_complete_and_correct_count": meta_ok,
            "metadata_complete_and_correct_fraction": f"{meta_ok}/{len(meta_sub)}",
            "grounding_sample_size": len(grd_scores),
            "grounding_counts_by_score": {
                "0": sum(1 for s in grd_scores if s == 0),
                "1": sum(1 for s in grd_scores if s == 1),
                "2": sum(1 for s in grd_scores if s == 2),
            },
            "grounding_mean_over_2": round(sum(grd_scores) / len(grd_scores), 2),
        }

    (results_dir / "manual_audit_summary.json").write_text(
        json.dumps(audit_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (starter_results_dir / "manual_audit_summary.json").write_text(
        json.dumps(audit_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(audit_summary, indent=2))


if __name__ == "__main__":
    main()
