from kfp import compiler,dsl
from pipelines.components.ingest import ingest

@dsl.pipeline(
    name="ingest-pipeline",
    description="ingestion kubeflow pipeline for ragops"
)
def ingest_pipeline():
    ingest_task = ingest()
    ingest_task.set_caching_options(False)
    ingest_task.set_cpu_request("2")
    ingest_task.set_memory_request("4Gi")
    ingest_task.set_env_variable("CHROMA_HOST", "chroma.ragops.svc.cluster.local")
    ingest_task.set_env_variable("CORPUS_BUCKET", "ragops-corpus-sec-filings-roop")
    ingest_task.set_env_variable("CHROMA_PORT", "8000")

if __name__ == "__main__":
    compiler.Compiler().compile(
        pipeline_func=ingest_pipeline,
        package_path="pipelines/ingest_pipeline.yaml"
    )
    print("Pipeline successfully compiled to 'pipelines/ingest_pipeline.yaml'!")
