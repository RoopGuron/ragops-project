"""Stage 1.5 of the query path: reorder retrieved chunks by relevance to the
question using a cross-encoder, a more accurate signal than cosine
similarity but too slow to run at ingestion scale, so applied only to
retrieve()'s narrowed top-k. Optional — when RERANKER_ENDPOINT is unset,
chunks pass through unchanged in their original retrieval order.
"""

import httpx
from rag.retriever import RetrievedChunk

def rerank(question: str, chunks: list[RetrievedChunk], endpoint: str) -> list[RetrievedChunk]:
    if not endpoint or not chunks:
        return chunks
    resp = httpx.post(
        f"{endpoint}/v1/models/reranker:predict",
        json={"query": question, "passages": [c.text for c in chunks]},
        timeout=5.0,
    )
    resp.raise_for_status()
    scored = sorted(zip(chunks, resp.json()["predictions"]), key=lambda cs: cs[1], reverse=True)
    return [c for c, _ in scored]


