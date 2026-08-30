"""Stage 1: load — read the extracted-item corpus (from pull_10k_corpus.py's
manifest.jsonl) into plain document dicts ready for chunking.

Kept deliberately dumb: this module knows nothing about chunking, embedding,
or Chroma. That separation is what makes each stage independently testable
and what let the SEC-extraction bugs earlier get caught by testing each
stage in isolation instead of only end-to-end.
"""

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MANIFEST = Path("corpus/clean/manifest.jsonl")

@dataclass
class Document:
    doc_id: str
    ticker: str
    accession: str
    item: str
    text: str
    fiscal_year: int | None = None


def _fiscal_year_from_accession(accession: str) -> int | None:
    # Accession numbers look like 0000796343-24-000006 — the middle segment
    # is the 2-digit filing year. Good enough for corpus metadata; not a
    # substitute for the actual period-of-report field if you need precision
    # later (available in the filing's own header, not parsed here yet).
    parts = accession.split("-")
    if len(parts) == 3 and len(parts[1]) == 2:
        yy = int(parts[1])
        return 2000 + yy
    return None


def load_documents(manifest_path: Path) -> list[Document]:
    docs = []
    with open(manifest_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            text_path = Path(row["path"])
            if not text_path.exists():
                print(f"WARNING: manifest references missing file {text_path}, skipping")
                continue

            docs.append(Document(
                doc_id=row["doc_id"],
                ticker=row["ticker"],
                accession=row["accession"],
                item=row["item"],
                text=text_path.read_text(),
                fiscal_year=_fiscal_year_from_accession(row["accession"]),
            ))

    print(f"loaded {len(docs)} documents from {manifest_path}")
    return docs
