import json
from dataclasses import asdict
from pathlib import Path

import mlflow
from mlflow import MlflowClient

from rag.config import RagConfig
from rag.serving import RagPipeline

WINNER_RUN_ID = "86e93f8be6c84159b0ba34d97d33cb29"
MODEL_NAME = "rag-query-path"

CHAMPION_CONFIG = Path("rag/champion_config.json")
_INFRA_KEYS = {"chroma_host", "chroma_port"}   # deployment config — stays in env, not in the file

# the winner, declared ONCE, here
cfg = RagConfig(top_k=12, per_doc_cap=3)
data = {k: v for k, v in asdict(cfg).items() if k not in _INFRA_KEYS}
CHAMPION_CONFIG.write_text(json.dumps(data, indent=2))

mlflow.set_experiment("RAG_Optimization_Engine")
with mlflow.start_run(run_id=WINNER_RUN_ID):          # attach to the winner run — keeps lineage
    info = mlflow.pyfunc.log_model(
        name="rag_pipeline",
        python_model=RagPipeline(),
        artifacts={"config": str(CHAMPION_CONFIG)},
        code_paths=["rag", "ingestion"],             # packages the modules into the model
        pip_requirements="requirements/serve.txt",
        registered_model_name=MODEL_NAME,
    )


client = MlflowClient()
version = info.registered_model_version
client.set_registered_model_alias(MODEL_NAME, "champion", version)   # MLflow 3.x: alias, not stage
client.update_model_version(
    MODEL_NAME, version,
    description=(
        "wide+capped: top_k=12, per_doc_cap=3, haiku generator. "
        "vs baseline 439cbc2b — recall 0.806->0.882, answer_relevancy 0.540->0.563, "
        "faithfulness 0.830->0.777 (within judge noise), context_precision ~0.18 (noisy; needs reranker, Week 3)."
    ),
)
print(f"registered {MODEL_NAME} v{version} @champion")
