"""CLI for the RAGAS Evaluation path — mirrors `python -m ingestion.pipeline`.

    # run a whole eval set -> one JSON line per question
    python -m evaluation.generate \
      --eval evaluation/eval/qa_eval_set.jsonl \
      --out artifacts/rag_run.jsonl \
      --top-k 8 \
      --per-doc-cap 2 \
      --model claude-sonnet-5

    python -m evaluation.rag_eval \
      --input_path artifacts/rag_run.jsonl \
      --run_id <run_id from eval above like 392a8b6ed77642a3992e504346dd33b7>

The --eval output is the hand-off artifact: the Day 2 "answers a handful
correctly" check reads it by eye, and Week 2's Ragas run consumes
{question, answer, contexts, reference_answer} from it. When the eval row
carries expected_sources, each record also gets a recall@k score so retrieval
quality is visible without spending any LLM tokens.
"""

import os
import anthropic
import argparse
import json
import time
import traceback
from pathlib import Path
from dataclasses import asdict

import mlflow
from contextlib import contextmanager

from rag.answer import answer_question, Answer
from rag.config import RagConfig
from ragas import EvaluationDataset, evaluate
from ragas.embeddings import BaseRagasEmbeddings
from ragas.llms import llm_factory
from ragas.metrics import Faithfulness, ResponseRelevancy, ContextPrecision

from ingestion.embedder import embed_texts


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
        raise ValueError("ANTHROPIC_WORKSPACE_ID is empty after cleaning.")

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
    parser.add_argument("--run_id", type=str, required=True, help="MLflow run ID to log metrics against")
    parser.add_argument("--model", default=_DEFAULTS.llm_model, help="judge LLM model id")
    parser.add_argument("--out", type=Path, help="write --eval results here (JSONL)")
    args = parser.parse_args()

    config = RagConfig(llm_model=args.model)

    mlflow.set_experiment("RAG_Optimization_Engine")
    with mlflow.start_run(run_id=args.run_id):
        run_ragas_eval(args.input_path, config)


if __name__ == "__main__":
    main()
