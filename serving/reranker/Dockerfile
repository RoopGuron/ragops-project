FROM python:3.12-slim

# 1. Setup system user and group
RUN groupadd -r ragops && useradd -r -g ragops -m ragops

# 2. Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3-venv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 3. Create the virtual environment using the clean 'venv' name
RUN python3 -m venv /opt/venv && \
    chown -R ragops:ragops /opt/venv

# 4. Configure application directory
WORKDIR /app
RUN chown ragops:ragops /app

# 5. Switch to non-root privileges
USER ragops

# 6. Copy source files with correct ownership permissions
COPY --chown=ragops:ragops serving/reranker ./serving/reranker
COPY --chown=ragops:ragops requirements/reranker.txt ./requirements/reranker.txt

# 7. Install python packages inside the custom venv location
RUN /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements/reranker.txt --extra-index-url https://download.pytorch.org/whl/cpu

# 8. Bake in the CrossEncoder model at build time, same as the ingest image.
RUN /opt/venv/bin/python -c \
  "from sentence_transformers import CrossEncoder; \
   CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2'); \
   CrossEncoder('cross-encoder/ms-marco-MiniLM-L-12-v2')"

ENV HF_HUB_OFFLINE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

# 9. Execution CrossEncoding Pipeline
CMD ["/opt/venv/bin/python", "-m", "serving.reranker.app"]
