"""Implement fixed-size (Strategy A) and heading/paragraph-aware (Strategies B & C) chunking."""
from __future__ import annotations

import re
from .models import Chunk, DocumentPage

HEADING_RE = re.compile(
    r"^(?:[1-9]\d*(?:\.\d+)*\.?\s+\S+|Appendix\s+[A-Z](?:\.\d+)*\.?\s+\S+)"
)


def is_heading(paragraph: str) -> bool:
    """Return True if a paragraph block is a short section/subsection heading."""
    lines = [ln.strip() for ln in paragraph.strip().splitlines() if ln.strip()]
    if len(lines) != 1:
        return False
    line = lines[0]
    if len(line) > 95 or line.endswith("."):
        return False
    return bool(HEADING_RE.match(line))


def fixed_size(page: DocumentPage, size: int = 500, overlap: int = 50) -> list[Chunk]:
    """Split page text into fixed-size character windows with overlap and retain page metadata."""
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be >= 0 and < size")

    text = page.text.strip()
    if not text:
        return []

    chunks: list[Chunk] = []
    step = size - overlap
    start = 0
    idx = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + size, text_len)
        window = text[start:end].strip()
        if window:
            meta = {
                **page.metadata,
                "document_id": page.document_id,
                "source": page.source,
                "page": page.page,
                "chunk_index": idx,
                "chunking_method": "fixed_size",
                "char_start": start,
                "char_end": end,
                "char_length": len(window),
            }
            chunks.append(
                Chunk(
                    chunk_id=f"{page.document_id}:p{page.page:02d}:fixed:{idx:02d}",
                    document_id=page.document_id,
                    source=page.source,
                    page=page.page,
                    text=window,
                    metadata=meta,
                )
            )
            idx += 1
        if end >= text_len:
            break
        start += step

    return chunks


def _split_oversized_paragraph(paragraph: str, max_size: int) -> list[str]:
    """Split a paragraph larger than max_size along sentence boundaries when possible."""
    if len(paragraph) <= max_size:
        return [paragraph]

    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    pieces: list[str] = []
    current = ""

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        candidate = f"{current} {sent}".strip() if current else sent
        if len(candidate) <= max_size:
            current = candidate
        else:
            if current:
                pieces.append(current)
            if len(sent) <= max_size:
                current = sent
            else:
                # Hard split only if a single sentence is longer than max_size
                for i in range(0, len(sent), max_size):
                    sub = sent[i : i + max_size].strip()
                    if sub:
                        pieces.append(sub)
                current = ""

    if current:
        pieces.append(current)
    return pieces


def by_paragraph(page: DocumentPage, max_size: int = 650) -> list[Chunk]:
    """Group paragraphs under headings, split oversized paragraphs by sentence, and retain metadata."""
    if max_size <= 0:
        raise ValueError("max_size must be positive")

    raw_paragraphs = [p.strip() for p in re.split(r"\n\s*\n", page.text) if p.strip()]
    if not raw_paragraphs:
        return []

    # Attach standalone section headings to the immediately following paragraph
    merged_blocks: list[tuple[str, str | None]] = []
    pending_heading: str | None = None
    active_section: str | None = page.metadata.get("section")

    for para in raw_paragraphs:
        if is_heading(para):
            active_section = para
            if pending_heading:
                pending_heading = f"{pending_heading}\n\n{para}"
            else:
                pending_heading = para
        else:
            if pending_heading:
                combined = f"{pending_heading}\n\n{para}"
                pending_heading = None
                merged_blocks.append((combined, active_section))
            else:
                merged_blocks.append((para, active_section))

    if pending_heading:
        if merged_blocks:
            prev_text, prev_sec = merged_blocks[-1]
            merged_blocks[-1] = (f"{prev_text}\n\n{pending_heading}", prev_sec)
        else:
            merged_blocks.append((pending_heading, active_section))

    # Split any oversized block along sentence boundaries
    sized_blocks: list[tuple[str, str | None]] = []
    for block_text, sec in merged_blocks:
        for sub_block in _split_oversized_paragraph(block_text, max_size=max_size):
            sized_blocks.append((sub_block, sec))

    # Greedily group consecutive blocks up to max_size
    grouped: list[tuple[str, str | None]] = []
    curr_text = ""
    curr_sec = active_section

    for block_text, sec in sized_blocks:
        if not curr_text:
            curr_text = block_text
            curr_sec = sec
            continue
        candidate = f"{curr_text}\n\n{block_text}"
        if len(candidate) <= max_size:
            curr_text = candidate
        else:
            grouped.append((curr_text, curr_sec))
            curr_text = block_text
            curr_sec = sec

    if curr_text:
        grouped.append((curr_text, curr_sec))

    chunks: list[Chunk] = []
    search_pos = 0
    for idx, (chunk_text, sec) in enumerate(grouped):
        first_line = chunk_text.splitlines()[0][:40]
        pos = page.text.find(first_line, search_pos)
        if pos == -1:
            pos = search_pos
        else:
            search_pos = pos
        meta = {
            **page.metadata,
            "document_id": page.document_id,
            "source": page.source,
            "page": page.page,
            "section": sec or page.metadata.get("section", "General"),
            "chunk_index": idx,
            "chunking_method": "by_paragraph",
            "char_start": pos,
            "char_end": pos + len(chunk_text),
            "char_length": len(chunk_text),
        }
        chunks.append(
            Chunk(
                chunk_id=f"{page.document_id}:p{page.page:02d}:para:{idx:02d}",
                document_id=page.document_id,
                source=page.source,
                page=page.page,
                text=chunk_text,
                metadata=meta,
            )
        )

    return chunks
