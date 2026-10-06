"""Stage 2: chunk — split each document's text into overlapping chunks sized
for embedding.

Written by hand rather than pulled in from a framework: chunking is the
single decision most likely to get tuned in week 2's MLflow comparison
(chunk size, overlap), so it's worth owning outright rather than treating as
a library black box. The strategy is a simple recursive splitter: try to
break on paragraph boundaries first, fall back to sentences, fall back to a
hard character cut only for a single run-on paragraph with no good break
point. Overlap keeps context from being severed exactly at a chunk boundary.
"""


import hashlib
import re
from dataclasses import dataclass

DEFAULT_CHUNK_SIZE = 1000   # characters, not tokens — good enough for a first pass;
DEFAULT_CHUNK_OVERLAP = 150  # revisit as token-based if eval scores call for it later
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8000
DEFAULT_COLLECTION = "sec_10k"

@dataclass
class Chunk:
    chunk_id: str
    text: str
    metadata: dict


_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _split_oversized(paragraph: str, size: int) -> list[str]:
    """Break one paragraph that's larger than the target chunk size —
    sentence boundaries first, then a hard character cut as a last resort."""
    sentences = _SENTENCE_SPLIT.split(paragraph)
    pieces, current = [], ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= size:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                pieces.append(current)
            if len(sentence) > size:
                # a single sentence longer than the chunk size — hard-cut it
                for i in range(0, len(sentence), size):
                    pieces.append(sentence[i:i + size])
                current = ""
            else:
                current = sentence
    if current:
        pieces.append(current)
    return pieces


def _chunk_text(
    text: str,
    size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]

    # Pass 1: greedily pack paragraphs into chunks near the target size.
    raw_chunks: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) <= size:
            current = candidate
            continue
        if current:
            raw_chunks.append(current)
        if len(para) > size:
            raw_chunks.extend(_split_oversized(para, size))
            current = ""
        else:
            current = para
    if current:
        raw_chunks.append(current)

    # Pass 2: add trailing overlap from the previous chunk so context isn't
    # severed exactly at a boundary.
    overlapped = []
    for i, c in enumerate(raw_chunks):
        if i == 0 or overlap == 0:
            overlapped.append(c)
        else:
            tail = raw_chunks[i - 1][-overlap:]
            overlapped.append(f"{tail}\n\n{c}")
    return overlapped

def chunk_document(doc, size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[Chunk]:
    """
    DAG Task (Per Document): Filters and chunks an individual file.
    """

    current_hash = hashlib.md5(doc.text.encode("utf-8")).hexdigest()

    pieces = _chunk_text(doc.text, size=size, overlap=overlap)
    return [
        Chunk(
            chunk_id=f"{doc.doc_id}_chunk{i}",
            text=piece,
            metadata={
                "doc_id": doc.doc_id,
                "doc_hash": current_hash,
                "ticker": doc.ticker,
                "accession": doc.accession,
                "item": doc.item,
                "fiscal_year": doc.fiscal_year,
                "chunk_index": i,
            },
        )
        for i, piece in enumerate(pieces)
    ]   
