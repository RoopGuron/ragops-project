from kfp import compiler, dsl, kubernetes

from pipelines.components.ingest import ingest
from pipelines.components.ragas_eval import ragas_eval


@dsl.pipeline(
    name="rag-pipeline",
    description="ingest, then offline eval --- ragops"
)
def rag_pipeline():
    ingest_task = ingest()
    ingest_task.set_caching_options(False)
    ingest_task.set_cpu_request("2")
    ingest_task.set_memory_request("4Gi")
    ingest_task.set_env_variable("CHROMA_HOST", "chroma.ragops.svc.cluster.local")
    ingest_task.set_env_variable("CORPUS_BUCKET", "ragops-corpus-sec-filings-roop")
    ingest_task.set_env_variable("CHROMA_PORT", "8000")

    eval_task = ragas_eval().after(ingest_task)
    eval_task.set_caching_options(False)
    eval_task.set_cpu_request("0.5")
    eval_task.set_memory_request("2Gi")
    eval_task.set_env_variable("CHROMA_HOST", "chroma.ragops.svc.cluster.local")
    eval_task.set_env_variable("MLFLOW_TRACKING_URI", "http://mlflow.ragops.svc.cluster.local:5000")
    kubernetes.use_secret_as_env(
        eval_task,
        secret_name="anthropic-credentials",
        secret_key_to_env={
            "ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY",
            "ANTHROPIC_WORKSPACE_ID": "ANTHROPIC_WORKSPACE_ID",
        },
    )

if __name__ == "__main__":
    compiler.Compiler().compile(
        pipeline_func=rag_pipeline,
        package_path="pipelines/rag_pipeline.yaml"
    )
    print("Pipeline successfully compiled to 'pipelines/rag_pipeline.yaml'!")
