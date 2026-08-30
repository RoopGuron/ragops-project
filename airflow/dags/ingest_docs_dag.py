"""Airflow DAG: load -> chunk -> embed_and_upsert.

Thin orchestration around the existing ingestion package (ingestion/loader.py,
chunker.py, embedder.py, vectorstore.py) — same stages as
`python -m ingestion.pipeline`, just split into four independently
retryable/observable Airflow tasks instead of one function call.

Documents, chunks, and embeddings are handed off between tasks via pickle
files under /opt/airflow/artifacts/<run_id>/ rather than XCom: XCom's
backing store (the Airflow metadata Postgres DB) isn't meant to carry tens
of thousands of chunk/embedding records between tasks. Only small summary
dicts go through XCom.

Imports of the ingestion package happen inside each task body (not at module
top level) so the scheduler's frequent DAG-file parsing doesn't pay the cost
of importing torch/chromadb just to register this DAG.

"""

import os
import pickle
from datetime import datetime
from pathlib import Path
from datetime import timedelta

from airflow.decorators import dag, task

PROJECT_ROOT = Path("/opt/airflow/project")
ARTIFACTS_ROOT = Path("/opt/airflow/artifacts")

# chromadb is reachable by service/container name on the shared `ragops_net`
# docker network (see local/docker-compose.yaml + airflow/docker-compose.yaml)
CHROMA_HOST = "chromadb"
CHROMA_PORT = 8000
COLLECTION_NAME = "sec_10k"


@dag(
    dag_id="ingest_docs",
    description="load -> chunk -> embed_and_upsert the SEC 10-K corpus into Chroma",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["ragops", "ingestion"],
)
def ingest_docs():

    @task()
    def load(**context) -> str:
        os.chdir(PROJECT_ROOT)
        from ingestion.loader import load_documents, DEFAULT_MANIFEST

        docs = load_documents(DEFAULT_MANIFEST)

        run_dir = ARTIFACTS_ROOT / context["run_id"]
        run_dir.mkdir(parents=True, exist_ok=True)
        docs_path = run_dir / "documents.pkl"
        with open(docs_path, "wb") as f:
            pickle.dump(docs, f)

        return str(docs_path)

    @task.external_python(python="/opt/ml-venv/bin/python", serializer="pickle",
                          execution_timeout=timedelta(minutes=30), retries=1)
    def chunk(docs_path: str) -> str:
        import hashlib
        import pickle
        import sys
        from pathlib import Path

        import chromadb

        sys.path.insert(0, "/opt/airflow/project")
        from ingestion.chunker import chunk_document, DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP

        # external_python runs in a fresh /opt/ml-venv interpreter — no access to
        # this module's globals, so the Chroma connection details are re-stated here.
        CHROMA_HOST = "chromadb"
        CHROMA_PORT = 8000
        COLLECTION_NAME = "sec_10k"

        with open(docs_path, "rb") as f:
            docs = pickle.load(f)

        # 1. Connect to your running Chroma remote container server
        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        collection = client.get_or_create_collection(name=COLLECTION_NAME)

        # 2. Extract incoming parent doc IDs and query Chroma for their hashes in a single call
        parent_doc_ids = [getattr(doc, "doc_id", str(i)) for i, doc in enumerate(docs)]
        query_batch_size = 100
        existing = {"metadatas": []}
        # Loop through the parent_doc_ids in blocks of 5,000
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

        print(f"existing {len(existing)} items for  {len(parent_doc_ids)} documents")


        existing_hashes = {}
        if existing and existing["metadatas"]:
            for meta in existing["metadatas"]:
                if meta and "doc_id" in meta and "doc_hash" in meta:
                    existing_hashes[meta["doc_id"]] = meta["doc_hash"]

        all_chunks = []
        parents_to_purge = []
        skipped_docs_count = 0
        for doc in docs:
            doc_id = getattr(doc, "doc_id", None)
            doc_text = getattr(doc, "text", "")
            doc_source = getattr(doc, "source", "unknown")

            current_hash = hashlib.md5(doc_text.encode("utf-8")).hexdigest()

            # Skip if the document hash hasn't shifted
            if doc_id in existing_hashes and existing_hashes[doc_id] == current_hash:
                skipped_docs_count += 1
                continue

            # Document is new or changed: track its ID for deletion down the line
            parents_to_purge.append(doc_id)
            all_chunks.extend(chunk_document(doc, size=DEFAULT_CHUNK_SIZE, overlap=DEFAULT_CHUNK_OVERLAP))

        print(f"Skipped {skipped_docs_count} unchanged documents.")
        print(f"Chunked {len(parents_to_purge)} new/modified docs into {len(all_chunks)} chunks.")

        # Save outputs to your shared filesystem artifacts folder
        run_dir = Path(docs_path).parent

        print(f"chunked {len(docs)} documents into {len(all_chunks)} chunks")
        chunks_path = run_dir / "chunks.pkl"
        with open(chunks_path, "wb") as f:
            pickle.dump(all_chunks, f)

        # Save a list of IDs we need to delete before inserting the new items
        purge_path = run_dir / "purge_ids.pkl"
        with open(purge_path, "wb") as f:
            pickle.dump(parents_to_purge, f)

        return str(chunks_path)

    @task.external_python(python="/opt/ml-venv/bin/python", serializer="pickle",
                          execution_timeout=timedelta(minutes=45), retries=1)
    def embed(chunks_path: str) -> str:
        import pickle
        import sys
        from pathlib import Path

        sys.path.insert(0, "/opt/airflow/project")
        from ingestion.embedder import embed_texts, DEFAULT_MODEL

        with open(chunks_path, "rb") as f:
            chunks = pickle.load(f)

        embeddings = embed_texts([c.text for c in chunks], model_name=DEFAULT_MODEL)

        embeddings_path = Path(chunks_path).parent / "embeddings.pkl"
        with open(embeddings_path, "wb") as f:
            pickle.dump(embeddings, f)

        return str(embeddings_path)

    @task.external_python(python="/opt/ml-venv/bin/python", serializer="pickle",
                            execution_timeout=timedelta(minutes=75), retries=1)
    def upsert(chunks_path: str, embeddings_path: str) -> str:
        import json
        import pickle
        import sys
        from pathlib import Path

        import chromadb

        sys.path.insert(0, "/opt/airflow/project")
        from ingestion.vectorstore import upsert_chunks

        with open(chunks_path, "rb") as f:
            chunks = pickle.load(f)

        with open(embeddings_path, "rb") as f:
            embeddings = pickle.load(f)

        run_dir = Path(chunks_path).parent
        purge_path = run_dir / "purge_ids.pkl"
        with open(purge_path, "rb") as f:
            parents_to_purge = pickle.load(f)

        # Short circuit early if everything was skipped and there's nothing to execute
        if not chunks:
            return json.dumps({"status": "Skipped. Collection is completely up to date.", "chunks": 0, "embeddings": 0})

        # 2. Connect to the Chroma Container Server
        client = chromadb.HttpClient(host="chromadb", port=8000)
        collection = client.get_or_create_collection(name="sec_10k")

        # 3. CRITICAL PURGE: Drop old version slices to prevent phantom/zombie chunk overlaps
        if parents_to_purge:
            print(f"Purging legacy chunks for modified files: {parents_to_purge}")
            collection.delete(where={"doc_id": {"$in": parents_to_purge}})

        collection = upsert_chunks(
            chunks, embeddings,
            host="chromadb", port=8000, collection_name="sec_10k",
        )

        return json.dumps({"collection": collection.name, "chunks": len(chunks), "embeddings": len(embeddings)})

    docs_path = load()
    chunks_path = chunk(docs_path)
    embeddings_path = embed(chunks_path)
    collection_info = upsert(chunks_path, embeddings_path)


ingest_docs()
