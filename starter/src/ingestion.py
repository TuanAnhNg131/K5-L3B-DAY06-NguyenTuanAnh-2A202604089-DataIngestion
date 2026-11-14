"""Read and normalize source data with page-level traceability and filtering of non-content pages."""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pypdf

from .models import DocumentPage

CORPUS_SPECS: list[dict[str, Any]] = [
    {
        "document_id": "rfc8693",
        "title": "RFC 8693: OAuth 2.0 Token Exchange",
        "source": "data/raw/rfc8693.pdf",
        "source_url": "https://www.rfc-editor.org/rfc/rfc8693.pdf",
        "license_or_permission": "IETF Trust Legal Provisions (TLP 5.0 / BCP 78) - Publicly redistributable specification",
        "year": 2020,
        "category": "Standards Track",
        "rfc_number": 8693,
    },
    {
        "document_id": "rfc8725",
        "title": "RFC 8725: JSON Web Token Best Current Practices",
        "source": "data/raw/rfc8725.pdf",
        "source_url": "https://www.rfc-editor.org/rfc/rfc8725.pdf",
        "license_or_permission": "IETF Trust Legal Provisions (TLP 5.0 / BCP 78) - Publicly redistributable specification",
        "year": 2020,
        "category": "Best Current Practice",
        "rfc_number": 8725,
    },
    {
        "document_id": "rfc9068",
        "title": "RFC 9068: JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens",
        "source": "data/raw/rfc9068.pdf",
        "source_url": "https://www.rfc-editor.org/rfc/rfc9068.pdf",
        "license_or_permission": "IETF Trust Legal Provisions (TLP 5.0 / BCP 78) - Publicly redistributable specification",
        "year": 2021,
        "category": "Standards Track",
        "rfc_number": 9068,
    },
    {
        "document_id": "rfc9126",
        "title": "RFC 9126: OAuth 2.0 Pushed Authorization Requests (PAR)",
        "source": "data/raw/rfc9126.pdf",
        "source_url": "https://www.rfc-editor.org/rfc/rfc9126.pdf",
        "license_or_permission": "IETF Trust Legal Provisions (TLP 5.0 / BCP 78) - Publicly redistributable specification",
        "year": 2021,
        "category": "Standards Track",
        "rfc_number": 9126,
    },
]


def normalize_text(text: str) -> str:
    """Normalize Unicode (NFKC) and whitespace without discarding paragraph/heading structure."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\u200b\u200c\u200d\ufeff\xad]", "", text)
    lines = []
    for line in text.split("\n"):
        cleaned = re.sub(r"[ \t\f\v]+", " ", line).strip()
        lines.append(cleaned)
    joined = "\n".join(lines)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip()


def _extract_page_raw_layout(pdf_page: Any) -> str:
    """Extract text from a pypdf Page preserving vertical line order and paragraph spacing."""
    lines_by_y: dict[float, list[tuple[float, str]]] = defaultdict(list)
    page_height = float(pdf_page.mediabox.height)

    def visitor(text: str, cm: Any, tm: Any, font_dict: Any, font_size: float) -> None:
        if not text or not text.strip():
            return
        raw_y = float(tm[5])
        y = round(raw_y if float(cm[3]) < 0 else (page_height - raw_y), 1)
        x = float(tm[4])
        lines_by_y[y].append((x, text.replace("\n", "")))

    pdf_page.extract_text(visitor_text=visitor)
    if not lines_by_y:
        return pdf_page.extract_text() or ""

    out_lines: list[str] = []
    prev_y: float | None = None
    for y in sorted(lines_by_y.keys()):
        # Skip running header (top of page) and running footer (bottom of page) on pages > 1
        if y < 58.0 or y > 720.0:
            continue
        fragments = lines_by_y[y]
        # Join fragments on the same visual line; avoid inserting spaces around ligatures
        parts: list[str] = []
        for idx, (_, frag) in enumerate(fragments):
            if idx == 0:
                parts.append(frag)
            else:
                prev_frag = parts[-1]
                if (
                    len(frag) == 1 and "\ufb00" <= frag <= "\ufb06"
                ) or (
                    len(prev_frag) == 1 and "\ufb00" <= prev_frag <= "\ufb06"
                ):
                    parts.append(frag)
                else:
                    parts.append(" " + frag)
        line_str = "".join(parts)
        if prev_y is not None and (y - prev_y) > 17.5:
            out_lines.append("")
        out_lines.append(line_str)
        prev_y = y

    return "\n".join(out_lines)


def classify_page_exclusion(page_num: int, normalized_text: str) -> str | None:
    """Return exclusion reason if a page is empty, TOC-only, references-only, or back-matter-only."""
    if not normalized_text or len(normalized_text.strip()) < 80:
        return "empty_or_near_empty"

    lines = [ln.strip() for ln in normalized_text.splitlines() if ln.strip()]
    first_line = lines[0] if lines else ""

    # Page 2 in all XMLv3 RFCs is the Table of Contents page
    if first_line.startswith("Table of Contents"):
        return "table_of_contents"

    # Detect pages that only contain bibliographic reference entries ([RFC...], [IANA...])
    ref_lines = sum(1 for ln in lines if re.match(r"^\[[A-Za-z0-9._-]+\]", ln))
    has_numbered_body_heading = any(
        re.match(r"^(?:[1-9]\d*(?:\.\d+)*\.?\s+[A-Z]|Appendix\s+[A-Z])", ln)
        and not re.match(r"^\d+(?:\.\d+)*\.?\s+(?:Normative|Informative)?\s*References\b", ln)
        for ln in lines
    )
    if ref_lines >= 2 and not has_numbered_body_heading:
        return "references_only"

    # Detect final Acknowledgements / Contributors / Authors' Addresses pages without body sections
    if (
        first_line.startswith(("Acknowledgements", "Acknowledgments", "Contributors", "Authors' Addresses", "Author's Address"))
        or ("Authors' Addresses" in normalized_text and not has_numbered_body_heading and page_num > 5)
        or ("Author's Address" in normalized_text and not has_numbered_body_heading and page_num > 5)
    ):
        if not has_numbered_body_heading:
            return "acknowledgements_or_authors_only"

    return None


def detect_primary_section(normalized_text: str, prev_section: str = "Introduction") -> str:
    """Detect the primary top-level RFC section heading on a page for metadata tracking."""
    for line in normalized_text.splitlines():
        line_s = line.strip()
        m = re.match(r"^([1-9]\d*)\.\s+([A-Z][A-Za-z0-9 ,()/\"'-]{2,60})$", line_s)
        if m:
            sec_num, sec_title = m.group(1), m.group(2).strip()
            if not sec_title.endswith(".") and "References" not in sec_title:
                return f"Section {sec_num}: {sec_title}"
        m_app = re.match(r"^(Appendix\s+[A-Z])\.\s+([A-Z][A-Za-z0-9 ,()/\"'-]{2,60})$", line_s)
        if m_app:
            return f"{m_app.group(1)}: {m_app.group(2).strip()}"
    if "Abstract" in normalized_text[:400]:
        return "Abstract & Overview"
    return prev_section


def load_pdf_with_audit(
    path: Path,
    document_id: str,
    source: str,
    base_metadata: dict[str, Any] | None = None,
) -> tuple[list[DocumentPage], dict[str, Any]]:
    """Extract physical pages, normalize text, filter non-content pages, and return audit log."""
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    reader = pypdf.PdfReader(str(path))
    valid_pages: list[DocumentPage] = []
    excluded_pages: list[dict[str, Any]] = []
    current_section = "Abstract & Overview"
    extra_meta = dict(base_metadata or {})

    for idx, pdf_page in enumerate(reader.pages, start=1):
        raw_text = _extract_page_raw_layout(pdf_page)
        norm_text = normalize_text(raw_text)

        # Remove trailing Table of Contents overflow on page 3 before "1. Introduction"
        if idx == 3 and "\n1. Introduction\n" in norm_text:
            intro_pos = norm_text.find("1. Introduction\n")
            norm_text = norm_text[intro_pos:].strip()

        exclusion_reason = classify_page_exclusion(idx, norm_text)
        if exclusion_reason is not None:
            excluded_pages.append(
                {
                    "page": idx,
                    "reason": exclusion_reason,
                    "char_count": len(norm_text),
                    "preview": norm_text[:120].replace("\n", " "),
                }
            )
            continue

        current_section = detect_primary_section(norm_text, prev_section=current_section)
        page_meta = {
            **extra_meta,
            "document_id": document_id,
            "source": source,
            "page": idx,
            "section": current_section,
            "char_count": len(norm_text),
        }
        valid_pages.append(
            DocumentPage(
                document_id=document_id,
                source=source,
                page=idx,
                text=norm_text,
                metadata=page_meta,
            )
        )

    audit_info = {
        "document_id": document_id,
        "source": source,
        "physical_pages": len(reader.pages),
        "valid_content_pages": len(valid_pages),
        "valid_page_numbers": [p.page for p in valid_pages],
        "excluded_pages_count": len(excluded_pages),
        "excluded_pages": excluded_pages,
        "total_normalized_chars": sum(len(p.text) for p in valid_pages),
    }
    return valid_pages, audit_info


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Extract each valid content page; keep its physical page number, source, and metadata."""
    spec = next((s for s in CORPUS_SPECS if s["document_id"] == document_id), {})
    base_meta = {
        k: v
        for k, v in spec.items()
        if k in ("year", "category", "rfc_number", "title")
    }
    pages, _ = load_pdf_with_audit(path, document_id=document_id, source=source, base_metadata=base_meta)
    return pages


def load_corpus(repo_root: Path) -> tuple[list[DocumentPage], dict[str, Any]]:
    """Load all corpus PDFs defined in CORPUS_SPECS and produce manifest + ingestion audit."""
    all_pages: list[DocumentPage] = []
    doc_manifests: list[dict[str, Any]] = []

    for spec in CORPUS_SPECS:
        pdf_path = repo_root / spec["source"]
        base_meta = {
            "year": spec["year"],
            "category": spec["category"],
            "rfc_number": spec["rfc_number"],
            "title": spec["title"],
        }
        pages, audit = load_pdf_with_audit(
            pdf_path,
            document_id=spec["document_id"],
            source=spec["source"],
            base_metadata=base_meta,
        )
        all_pages.extend(pages)
        doc_manifests.append(
            {
                "source_id": spec["document_id"],
                "title": spec["title"],
                "source_path_or_url": spec["source_url"],
                "local_path": spec["source"],
                "license_or_permission": spec["license_or_permission"],
                "accessed_at": "2026-11-14T10:56:00+07:00",
                "snapshot_or_version": f"RFC {spec['rfc_number']} ({spec['year']}, {spec['category']})",
                "year": spec["year"],
                "category": spec["category"],
                "physical_pages": audit["physical_pages"],
                "valid_content_pages": audit["valid_content_pages"],
                "valid_page_ids": [f"{spec['document_id']}:p{p:02d}" for p in audit["valid_page_numbers"]],
                "valid_page_numbers": audit["valid_page_numbers"],
                "excluded_pages": audit["excluded_pages"],
                "character_count": audit["total_normalized_chars"],
                "page_character_counts": {str(p.page): len(p.text) for p in pages},
            }
        )

    manifest = {
        "corpus_title": "IETF OAuth 2.0 & JWT Security Specifications Corpus",
        "topic": "Technical Specifications for OAuth 2.0 Token Exchange, JWT Best Current Practices, JWT Access Tokens, and Pushed Authorization Requests",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "page_counting_rule": (
            "Count physical PDF pages containing substantive technical specification text after Unicode NFKC "
            "normalization and running header/footer removal. Exclude pages containing only Table of Contents, "
            "only Bibliographic References, or only Acknowledgements / Authors' Addresses. Strip trailing TOC lines "
            "on Page 3 prior to Section 1. Introduction."
        ),
        "total_documents": len(doc_manifests),
        "total_physical_pages": sum(d["physical_pages"] for d in doc_manifests),
        "total_valid_content_pages": sum(d["valid_content_pages"] for d in doc_manifests),
        "total_normalized_characters": sum(d["character_count"] for d in doc_manifests),
        "metadata_fields": {
            "document_id": "str - RFC identifier (rfc8693, rfc8725, rfc9068, rfc9126)",
            "source": "str - Relative path to source PDF in repository",
            "page": "int - Physical page number in the PDF (1-indexed)",
            "year": "int - Official IETF publication year (2020 or 2021), used for metadata filtering",
            "category": "str - IETF RFC status category ('Standards Track' or 'Best Current Practice'), used for metadata filtering",
            "section": "str - Primary numbered section heading on the page",
        },
        "documents": doc_manifests,
    }
    return all_pages, manifest
