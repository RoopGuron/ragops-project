"""RAGAS judge — score an already-generated RAG run and log metrics to MLflow.

Stage 2 of the offline eval pipeline. Consumes the JSONL that
`evaluation.generate` writes ({question, answer, contexts, reference_answer}
per line) and adds three LLM-judged metrics to an existing run:

    faithfulness       - every claim in the answer grounded in the contexts
    answer_relevancy   - the answer actually addresses the question
    context_precision  - retrieved contexts are relevant and well ranked

    python -m evaluation.generate \\
        --eval evaluation/eval/qa_eval_set.jsonl \\
        --out artifacts/rag_run.jsonl --top-k 12 --per-doc-cap 3
    # prints a run_id; params + mean_recall are logged there

    python -m evaluation.ragas_eval \\
        --input_path artifacts/rag_run.jsonl --run_id <that run_id>
    # faithfulness / answer_relevancy / context_precision land on the SAME run

--run_id is required: the judge always appends to the generate-stage run so a
single MLflow row carries params + recall + judge metrics — that row is what
the sweep comparison in the UI reads.

RAGAS is pinned to 0.4.3 (requirements/eval.in): run_ragas_eval carries
version-specific workarounds — the _map_provider_params monkeypatch and the
_ProjectEmbeddings wrapper. Re-verify both on any ragas bump.
"""


# 1. Standard library imports
import argparse
import json
import os
from pathlib import Path

# 2. Third-party cloud/ML clients (anthropic, mlflow)
import anthropic
import mlflow

# 3. Third-party evaluation framework (ragas)
from ragas import EvaluationDataset, evaluate
from ragas.embeddings import BaseRagasEmbeddings
from ragas.llms import llm_factory
from ragas.metrics import ContextPrecision, Faithfulness, ResponseRelevancy

# 4. Local application imports
from ingestion.embedder import embed_texts
from rag.config import RagConfig

_DEFAULTS = RagConfig()


class _ProjectEmbeddings(BaseRagasEmbeddings):
    """Wraps ingestion.embedder.embed_texts so RAGAS judges similarity with the
    exact same sentence-transformers model chunking used — instead of ragas's
    own HuggingfaceEmbeddings, whose legacy class is abstract-incomplete in
    0.4.3 (missing aembed_query/aembed_documents, so it can't be instantiated).
    """

    def __init__(self, model_name: str):
        super().__init__()
        self.model_name = model_name

    def embed_query(self, text: str) -> list[float]:
        return embed_texts([text], model_name=self.model_name)[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return embed_texts(texts, model_name=self.model_name)

    async def aembed_query(self, text: str) -> list[float]:
        return self.embed_query(text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts)


def _load_eval_dataset(path: Path) -> EvaluationDataset:
    records = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        records.append({
            "user_input": rec["question"],
            "response": rec["answer"],
            "retrieved_contexts": rec["contexts"],
            "reference": rec.get("reference_answer"),  # None for rows without one — comes through as NaN on context_precision
        })
    return EvaluationDataset.from_list(records)


def run_ragas_eval(input_file: Path, config: RagConfig) -> None:
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not workspace_id:
        raise ValueError("ANTHROPIC_WORKSPACE_ID is not set.")

    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set.")

    client = anthropic.Anthropic(
        api_key=api_key,
        default_headers={"anthropic-workspace-id": workspace_id} if workspace_id else None
    )

    ragas_llm = llm_factory(model=config.llm_model, provider="anthropic", client=client, max_tokens=4096)
    # Workaround: RAGAS 0.4.3's InstructorModelArgs always sends BOTH temperature
    # and top_p to Anthropic, but Claude 5-era models reject having both set at
    # once (and claude-sonnet-5/opus-5 reject temperature outright). Drop both
    # and let the model use its own default sampling. Remove this once RAGAS
    # ships proper support for the newer effort-based Anthropic models.
    ragas_llm._map_provider_params = lambda: {"max_tokens": ragas_llm.model_args["max_tokens"]}
    ragas_embeddings = _ProjectEmbeddings(model_name=config.embedding_model)

    eval_dataset = _load_eval_dataset(input_file)

    metrics = [
        Faithfulness(llm=ragas_llm),
        ResponseRelevancy(llm=ragas_llm),
        ContextPrecision(llm=ragas_llm),
    ]

    result = evaluate(eval_dataset, metrics=metrics, llm=ragas_llm, embeddings=ragas_embeddings)

    mlflow.log_metric("faithfulness", sum(result["faithfulness"]) / len(result["faithfulness"]))
    mlflow.log_metric("answer_relevancy", sum(result["answer_relevancy"]) / len(result["answer_relevancy"]))
    mlflow.log_metric("context_precision", sum(result["context_precision"]) / len(result["context_precision"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the RAGAs evaluation on the RAG run results")
    parser.add_argument("--input_path", type=Path, required=True, help="path to the input JSONL file for evaluation")
    parser.add_argument("--run_id", required=True, help="the generate-stage MLflow run to append judge metrics to — keeps params, recall, and judge scores on one run")
    parser.add_argument("--model", default=_DEFAULTS.llm_model, help="judge LLM model id")
    args = parser.parse_args()

    config = RagConfig(llm_model=args.model)

    mlflow.set_experiment("RAG_Optimization_Engine")
    with mlflow.start_run(run_id=args.run_id):
        run_ragas_eval(args.input_path, config)


if __name__ == "__main__":
    main()
