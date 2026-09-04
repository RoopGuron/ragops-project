"""Central config for the RAG query path.

One frozen dataclass holding every knob the query path exposes. Week 2's
MLflow run logs these fields as params, so anything worth sweeping later
(top_k, llm_model, prompt_version, per-doc cap) lives here as a field rather
than as a default argument scattered across four modules.

CHROMA_HOST / CHROMA_PORT read from the environment so the same code runs
against localhost:8000 locally and chromadb:8000 inside the Airflow docker
network (same pattern as airflow/dags/ingest_docs_dag.py).
"""

import os
from dataclasses import dataclass

from ingestion.embedder import DEFAULT_MODEL as DEFAULT_EMBEDDING_MODEL

# DEFAULT_LLM_MODEL = "claude-opus-5"
# cheaper eval loops
DEFAULT_LLM_MODEL = "claude-sonnet-5"
DEFAULT_COLLECTION = "sec_10k"


@dataclass(frozen=True)
class RagConfig:
    chroma_host: str = os.getenv("CHROMA_HOST", "localhost")
    chroma_port: int = int(os.getenv("CHROMA_PORT", "8000"))
    collection_name: str = DEFAULT_COLLECTION

    # MUST match the model ingestion embedded the corpus with — a mismatch
    # means the query vector lands in a different space than the chunks.
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    llm_model: str = DEFAULT_LLM_MODEL

    top_k: int = 8
    per_doc_cap: int | None = None   # keep at most N chunks per doc_id before prompting
    fanout: bool = False             # entity-aware multi-query retrieval (not wired up yet)

    max_context_chars: int = 32000   # ~8k tokens; drop lowest-ranked chunks past this
    max_tokens: int = 1024           # LLM answer cap

    prompt_version: str = "answer_v1"
