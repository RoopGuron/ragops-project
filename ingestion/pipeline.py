"""Orchestrates load -> chunk -> embed -> upsert.

Deliberately a plain function, not an Airflow DAG. Tomorrow's DAG wraps
run_ingestion()'s four stages as tasks (or calls this module's functions
directly from PythonOperators/@task) — the logic doesn't change, only how
it's scheduled and retried. Testing this end-to-end today only requires
`docker-compose up chroma` and a Python environment, not a running Airflow
scheduler.
"""


import argparse
import hashlib
from pathlib import Path

import chromadb

from ingestion.chunker import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, chunk_document
from ingestion.embedder import DEFAULT_MODEL, embed_texts
from ingestion.loader import DEFAULT_MANIFEST, load_documents
from ingestion.vectorstore import (
    DEFAULT_COLLECTION,
    DEFAULT_HOST,
    DEFAULT_PORT,
    upsert_chunks,
)


def run_ingestion(
    manifest_path: Path = DEFAULT_MANIFEST,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    embedding_model: str = DEFAULT_MODEL,
    chroma_host: str = DEFAULT_HOST,
    chroma_port: int = DEFAULT_PORT,
    collection_name: str = DEFAULT_COLLECTION,
) -> dict:
    # 1. load
    docs = load_documents(manifest_path)
    if not docs:
        print("no documents to ingest — check that pull_10k_corpus.py has been run")
        return {"documents": 0, "skipped": 0, "chunks": 0}


    # 2. chunk
    # Connect to your running Chroma remote container server
    client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
    collection = client.get_or_create_collection(name=collection_name)

    # Extract incoming parent doc IDs and query Chroma for their hashes in a single call
    parent_doc_ids = [getattr(doc, "doc_id", str(i)) for i, doc in enumerate(docs)] # Assumes doc object has an .id attribute
    query_batch_size = 100
    existing = {"metadatas": []}
    # Loop through the parent_doc_ids in blocks of 100
    for i in range(0, len(parent_doc_ids), query_batch_size):
        batch_ids = parent_doc_ids[i : i + query_batch_size]
        
        results = collection.get(
            where={"doc_id": {"$in": batch_ids}},  # Only 5,000 variables at a time
            include=["metadatas"]
        )
        
        # Check if we actually got metadata back
        if results and "metadatas" in results and results["metadatas"]:
            print(f"Fetched batch: found {len(results['metadatas'])} records")
            existing["metadatas"].extend(results["metadatas"])

    print(f"Total metadata records retrieved: {len(existing['metadatas'])}")

    print(f"existing {len(existing['metadatas'])} items for  {len(parent_doc_ids)} documents")

    existing_hashes = {}
    if existing and existing["metadatas"]:
        for meta in existing["metadatas"]:
            if meta and "doc_id" in meta and "doc_hash" in meta:
                existing_hashes[meta["doc_id"]] = meta["doc_hash"]

    all_chunks = []
    parents_to_purge = []
    skipped_docs_count = 0

    all_chunks = []
    for doc in docs:
        doc_id = getattr(doc, "doc_id", None)
        doc_text = getattr(doc, "text", "")
        
        current_hash = hashlib.md5(doc_text.encode("utf-8")).hexdigest()

        # Skip if the document hash hasn't shifted
        if doc_id in existing_hashes and existing_hashes[doc_id] == current_hash:
            skipped_docs_count += 1
            continue

        # Document is new or changed: track its ID for deletion down the line
        parents_to_purge.append(doc_id)

        all_chunks.extend(chunk_document(doc, size=chunk_size, overlap=chunk_overlap))

    print(f"chunked {len(docs)} documents into {len(all_chunks)} chunks "
          f"(avg {len(all_chunks) / len(docs):.1f} chunks/doc)")

    # 3. embed
    embeddings = embed_texts([c.text for c in all_chunks], model_name=embedding_model)

    # 4. upsert
    # Short circuit early if everything was skipped and there's nothing to execute
    if not all_chunks:
        return {"documents": len(docs), "skipped": skipped_docs_count, "chunks": 0}


    # 2. Connect to the Chroma Container Server
    client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
    collection = client.get_or_create_collection(name=collection_name)

    # 3. CRITICAL PURGE: Drop old version slices to prevent phantom/zombie chunk overlaps
    if parents_to_purge:
        print(f"Purging legacy documents {len(parents_to_purge)} for modified or new docs ")
        collection.delete(where={"doc_id": {"$in": parents_to_purge}})

    upsert_chunks(
        all_chunks, embeddings,
        host=chroma_host, port=chroma_port, collection_name=collection_name,
    )

    return {"documents": len(docs), "skipped": skipped_docs_count, "chunks": len(all_chunks)}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the RAGOps ingestion pipeline")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--chroma-host", default=DEFAULT_HOST)
    parser.add_argument("--chroma-port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    args = parser.parse_args()

    result = run_ingestion(
        manifest_path=args.manifest,
        chroma_host=args.chroma_host,
        chroma_port=args.chroma_port,
        collection_name=args.collection,
    )
    print(f"done: {result}")
