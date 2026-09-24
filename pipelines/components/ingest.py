from kfp import dsl

@dsl.container_component
def ingest():
    """Load corpus/clean/ from GCS, then chunk, embed and upsert into Chroma."""

    return dsl.ContainerSpec(
        image="ghcr.io/roopguron/ragops-ingestion:0.0.1",
        command=["/opt/venv/bin/python", "-m", "ingestion.kfp_entrypoint"],
    )
