FROM apache/airflow:2.10.4-python3.12

# --- ML venv: chromadb / sentence-transformers / torch live here, fully
# isolated from Airflow's own site-packages so they never have to reconcile
# with apache-airflow-providers-google's pandas<2.2 pin. Only the `embed`
# and `upsert` DAG tasks run against this interpreter, via
# @task.external_python(python="/opt/ml-venv/bin/python").

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-venv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/ml-venv \
    && chown -R airflow:0 /opt/ml-venv

USER airflow
COPY ml-requirements.txt /ml-requirements.txt
RUN /opt/ml-venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/ml-venv/bin/pip install --no-cache-dir -r /ml-requirements.txt

