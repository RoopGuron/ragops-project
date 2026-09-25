"""KFP pod entrypoint for the offline eval — generate RAG answers over the
eval set, then attach RAGAS judge scores to the same MLflow run.

Runs evaluation.generate then evaluation.ragas_eval in one process, so the
run_id passes in memory instead of between pods. Only used in-cluster; locally
the two scripts are run separately (see evaluation/generate.py).

Needs MLFLOW_TRACKING_URI, CHROMA_HOST, ANTHROPIC_API_KEY and
ANTHROPIC_WORKSPACE_ID in the environment (the last two from a K8s Secret).
"""


from pathlib import Path
import mlflow
from evaluation.generate import run_eval
from evaluation.ragas_eval import run_ragas_eval
from rag.config import RagConfig

ARTIFACTS_PATH = "artifacts/rag_run.jsonl"
EVAL_PATH = "evaluation/eval/qa_eval_set.jsonl"
LLM_MODEL = "claude-haiku-4-5-20251001"
CHROMA_HOST = "chroma.ragops.svc.cluster.local"

if __name__ == "__main__":
    config = RagConfig(chroma_host=CHROMA_HOST, top_k=12, per_doc_cap=3)
    run_id = run_eval(Path(EVAL_PATH) , Path(ARTIFACTS_PATH), config)
    if run_id is None :
        raise ValueError("Evaluation Not Run")

    print(f"generate done: {run_id}")

    mlflow.set_experiment("RAG_Optimization_Engine")
    with mlflow.start_run(run_id=run_id):
        run_ragas_eval(Path(ARTIFACTS_PATH), config)

    print(f"ragas eval done: {run_id}")