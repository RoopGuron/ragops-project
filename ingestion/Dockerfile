FROM python:3.14-slim

# 1. Setup system user and group
RUN groupadd -r ragops && useradd -r -g ragops -m ragops

# 2. Install system dependencies (including curl for the healthcheck)
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3-venv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 3. Create the virtual environment using the clean 'venv' name
RUN python3 -m venv /opt/venv && \
    chown -R ragops:ragops /opt/venv && \
    mkdir -p /opt/corpus && \
    chown -R ragops:ragops /opt/corpus

# 4. Configure application directory
WORKDIR /ingestion-app
RUN chown ragops:ragops /ingestion-app

# 5. Switch to non-root privileges
USER ragops

# 6. Copy source files with correct ownership permissions
COPY --chown=ragops:ragops ingestion/ ./ingestion/
COPY --chown=ragops:ragops requirements/ingest.txt ./requirements/ingest.txt

# 7. Install python packages inside the custom venv location
RUN /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements/ingest.txt --extra-index-url https://download.pytorch.org/whl/cpu

RUN /opt/venv/bin/python -c \
  "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

ENV HF_HUB_OFFLINE=1

# 9. Execution Ingestion Pipeline
CMD ["/opt/venv/bin/python", "-m", "ingestion.kfp_entrypoint"]

