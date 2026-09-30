"""KServe custom predictor that reranks retrieved passages against a query
using a cross-encoder, for use after Chroma retrieval in the RAG path.

Wraps sentence_transformers.CrossEncoder — scores each (query, passage) pair
directly rather than comparing separately-embedded vectors, which is more
accurate than cosine similarity but too slow to run at ingestion scale, so
it's only applied to the top-k chunks retrieve() already narrowed down.
Takes {"query": str, "passages": [str, ...]} and returns
{"predictions": [float, ...]}, one relevance score per passage, in the same
order as the input.
"""

import kserve
import os
import torch
from kserve.errors import InvalidInput
from sentence_transformers import CrossEncoder

class Reranker(kserve.Model):
    def __init__(self, name: str):
        super().__init__(name)
        threads = os.environ.get("OMP_NUM_THREADS")
        if threads:
            torch.set_num_threads(int(threads))
        print(f"KServe Container Initialized - OMP_NUM_THREADS: {threads or 'not set'}")
        self.load()

    def load(self):
        checkpoint = os.environ.get("MODEL_CHECKPOINT", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        print(f"Loading reranker checkpoint: {checkpoint}")
        self.model = CrossEncoder(checkpoint)
        self.ready = True

    def predict(self, payload: dict, headers: dict = None) -> dict:
        if payload is None or "query" not in payload \
                    or "passages" not in payload \
                    or not isinstance(payload["query"],str) \
                    or not isinstance(payload["passages"],list) \
                    or not all(isinstance(t, str) for t in payload["passages"]):
                    raise InvalidInput("The request body must be JSON like {\"query\": \"text\",\"passages\": [\"text\"]}")
        # 1. Extract the components
        query = payload["query"]
        passages = payload["passages"]

        # 2. Form pairs for the model
        pairs = [(query, passage) for passage in passages]
        scores = self.model.predict(pairs)
        print(scores)

        return {"predictions": scores.tolist()}

if __name__=="__main__":
    model_name = os.environ.get("MODEL_NAME", "reranker")
    kserve.ModelServer().start([Reranker(model_name)])