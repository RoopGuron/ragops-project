"""Stage 1 of the query path: question -> top-k chunks from Chroma.

No LLM here — this module is independently testable against a running Chroma
container alone (`docker-compose up chromadb`), the same way each ingestion
stage was validated in isolation.

Two things it has to get right:

1. The query is embedded with the *same* local sentence-transformers model
   ingestion used (ingestion.embedder.embed_texts). Chroma holds no embedding
   function of its own here — vectors were supplied at upsert — so the query
   vector must be handed in via query_embeddings, never query_texts (that
   would make Chroma reach for its own default model and a dim mismatch).

2. metadata["item"] is the raw item title from the manifest
   ("ITEM 1A. Risk Factors"), not the "item1a" selector the eval set's
   expected_sources and the answer citations use. The clean token is the
   doc_id suffix (..._item1a.), so it's normalised from there.
"""

import re
from dataclasses import dataclass

import chromadb
import httpx  # already in the dependency tree via chromadb — no new package needed

from ingestion.embedder import DEFAULT_MODEL, embed_texts
from rag.config import DEFAULT_COLLECTION


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    ticker: str
    fiscal_year: int | None
    item: str            # normalised: item1 | item1a | item7 | item7a | ...
    doc_id: str
    accession: str
    chunk_index: int
    distance: float      # cosine distance from Chroma; lower = closer

    @property
    def selector(self) -> str:
        """`SNOW/2024/item7a` — same shape as the eval set's expected_sources."""
        return f"{self.ticker}/{self.fiscal_year}/{self.item}"


_ITEM_FROM_DOC_ID = re.compile(r"_(item[0-9]+[a-z]?)\.?$", re.IGNORECASE)
_ITEM_FROM_TITLE = re.compile(r"\s*item\s*([0-9]+)\s*([a-z]?)", re.IGNORECASE)


def _normalise_item(doc_id: str, metadata_item: str) -> str:
    m = _ITEM_FROM_DOC_ID.search(doc_id or "")
    if m:
        return m.group(1).lower()
    # fall back to squashing the raw title: "ITEM 1A. Risk Factors" -> "item1a"
    m = _ITEM_FROM_TITLE.match(metadata_item or "")
    if m:
        return f"item{m.group(1)}{m.group(2).lower()}"
    return (metadata_item or "unknown").strip().lower()


def _to_chunk(chunk_id: str, text: str, meta: dict | None, distance: float | None) -> RetrievedChunk:
    meta = meta or {}
    doc_id = meta.get("doc_id", "")
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text or "",
        ticker=meta.get("ticker", "?"),
        fiscal_year=meta.get("fiscal_year"),
        item=_normalise_item(doc_id, meta.get("item", "")),
        doc_id=doc_id,
        accession=meta.get("accession", ""),
        chunk_index=meta.get("chunk_index", -1),
        distance=float(distance) if distance is not None else float("nan"),
    )


def retrieve(
    question: str,
    *,
    top_k: int = 8,
    where: dict | None = None,
    host: str = "localhost",
    port: int = 8000,
    collection_name: str = DEFAULT_COLLECTION,
    embedding_model: str = DEFAULT_MODEL,
    embedding_endpoint: str = "",
) -> list[RetrievedChunk]:
    if not question or not question.strip():
        return []

    if embedding_endpoint:
        resp = httpx.post(
            f"{embedding_endpoint}/v1/models/embedder:predict",
            json={"instances": [question]},
            timeout=5.0,
        )
        resp.raise_for_status()
        q_emb = resp.json()["predictions"][0]
    else:
        q_emb = embed_texts([question], model_name=embedding_model)[0]

    client = chromadb.HttpClient(host=host, port=port)
    # Name only — the collection already exists; re-passing its hnsw metadata
    # can raise a conflict on some Chroma versions (see vectorstore.py vs
    # pipeline.py, which disagree on this).
    collection = client.get_or_create_collection(collection_name)

    res = collection.query(
        query_embeddings=[q_emb],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    # Chroma returns List[List[...]] keyed by query embedding; we sent one.
    rows = zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])
    return [_to_chunk(*row) for row in rows]


def cap_per_doc(chunks: list[RetrievedChunk], cap: int) -> list[RetrievedChunk]:
    """Keep at most `cap` chunks per doc_id, preserving retrieval order.

    Plain top-k piles up on the single closest filing; the eval set's
    over-time / cross-company questions need chunks from *several* filings to
    answer at all. This is the cheapest lever for that (design doc, section 5).
    """
    seen: dict[str, int] = {}
    kept: list[RetrievedChunk] = []
    for c in chunks:
        n = seen.get(c.doc_id, 0)
        if n >= cap:
            continue
        seen[c.doc_id] = n + 1
        kept.append(c)
    return kept
