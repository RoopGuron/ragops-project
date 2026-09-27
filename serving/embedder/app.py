"""KServe custom predictor that embeds text with the project's sentence-
transformers model, for query-time embedding in the RAG path.

Wraps ingestion.embedder.embed_texts, so serving uses the same model as
ingestion and query vectors stay comparable to the indexed chunks. Takes
{"instances": [text, ...]} and returns {"predictions": [[float, ...], ...]}.
Ingestion still embeds documents in-process; only queries go through here.
"""


import kserve
import os
import torch
from kserve.errors import InvalidInput
from ingestion.embedder import embed_texts

class Embedder(kserve.Model):
    def __init__(self, name: str):
        super().__init__(name)
        threads = os.environ.get("OMP_NUM_THREADS")
        if threads:
            torch.set_num_threads(int(threads))
        print(f"KServe Container Initialized - OMP_NUM_THREADS: {threads or 'not set'}")
        self.load()

    def load(self):
        embed_texts(["warmup"])
        self.ready = True

    def predict(self, payload: dict, headers: dict = None) -> dict:
        if payload is None or "instances" not in payload \
            or not isinstance(payload["instances"],list) \
            or not all(isinstance(t, str) for t in payload["instances"]):
            raise InvalidInput("The request body must be JSON like {\"instances\": [\"text\"]}")
        return {"predictions": embed_texts(payload["instances"])}

if __name__=="__main__":
    kserve.ModelServer().start([Embedder("embedder")])