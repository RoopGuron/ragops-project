"""Stage 4: upsert — write chunks + embeddings into Chroma, running as the
Docker server (chromadb/chroma image), not the embedded/local-file client.

Uses upsert rather than add on purpose: chunk_id is deterministic
(doc_id + chunk index), so re-running ingestion after a filing changes
overwrites that filing's old chunks instead of duplicating them. That's the
same idempotency the incremental-ingestion logic (week 1, tomorrow) and the
Kafka-triggered re-ingestion (week 2) both depend on.
"""

import os

import chromadb

DEFAULT_HOST = os.getenv("CHROMA_HOST", "localhost")
DEFAULT_PORT = int(os.getenv("CHROMA_PORT", "8000"))

DEFAULT_COLLECTION = "sec_10k"
UPSERT_BATCH_SIZE = 100  # stay comfortably under Chroma's per-request payload limit


def get_client(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    return chromadb.HttpClient(host=host, port=port)


def get_collection(client, name: str = DEFAULT_COLLECTION):
    # cosine distance is the standard choice for sentence-transformers
    # embeddings, which are trained/normalized for cosine similarity
    return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def upsert_chunks(chunks, embeddings, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                   collection_name: str = DEFAULT_COLLECTION):
    assert len(chunks) == len(embeddings), "chunks and embeddings must be the same length"

    client = get_client(host, port)
    collection = get_collection(client, collection_name)

    for i in range(0, len(chunks), UPSERT_BATCH_SIZE):
        batch = chunks[i:i + UPSERT_BATCH_SIZE]
        batch_embeddings = embeddings[i:i + UPSERT_BATCH_SIZE]
        collection.upsert(
            ids=[c.chunk_id for c in batch],
            embeddings=batch_embeddings,
            documents=[c.text for c in batch],
            metadatas=[c.metadata for c in batch],
        )
        print(f"upserted {i + len(batch)}/{len(chunks)} chunks")

    return collection
