"""Stage 3: embed — turn chunk text into vectors with a local sentence-
transformers model.

Local model (not an API call) on purpose: it's what week 3 serves via
KServe as its own InferenceService, so ingestion and serving should use the
same model from the start rather than switching later. all-MiniLM-L6-v2 is
the default here as a fast, well-known baseline (384-dim); week 2's MLflow
comparison is where a stronger candidate (e.g. bge-small-en-v1.5) gets
measured against it on the eval set rather than assumed better.
"""

from functools import lru_cache

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=4)
def _get_model(model_name: str):
    # Imported lazily and cached per model name so importing this module
    # doesn't require sentence-transformers/torch unless embedding is
    # actually called — keeps loader.py/chunker.py unit tests fast.
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)


def embed_texts(texts: list[str], model_name: str = DEFAULT_MODEL, batch_size: int = 32) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model(model_name)
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=len(texts) > 200,
        convert_to_numpy=True,
    )
    return embeddings.tolist()
