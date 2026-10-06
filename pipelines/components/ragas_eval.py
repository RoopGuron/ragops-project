import os

from kfp import dsl


@dsl.container_component
def ragas_eval():
    """Generate RAG answers over the eval set, then add RAGAS judge scores.

    Runs evaluation.generate followed by evaluation.ragas_eval in one pod and
    logs params, recall and faithfulness / answer_relevancy / context_precision
    to a single MLflow run. Needs CHROMA_HOST, MLFLOW_TRACKING_URI and the
    Anthropic credentials (Secret) set on the task.
    """

    return dsl.ContainerSpec(
        image=os.environ.get("EVAL_IMAGE", "ghcr.io/roopguron/ragops-evaluation:0.0.1"),
        command=["/opt/venv/bin/python", "-m", "evaluation.kfp_entrypoint"],
    )
