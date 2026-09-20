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
    chown -R ragops:ragops /opt/venv


# 4. Configure application directory
WORKDIR /app
RUN chown ragops:ragops /app

# 5. Switch to non-root privileges
USER ragops

# 6. Copy source files with correct ownership permissions
COPY --chown=ragops:ragops rag/ ./rag/
COPY --chown=ragops:ragops ingestion/ ./ingestion/
COPY --chown=ragops:ragops requirements/ ./requirements/

# 7. Install python packages inside the custom venv location
RUN /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements/serve.txt --extra-index-url https://download.pytorch.org/whl/cpu

EXPOSE 8000

# 8. Container health monitor
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)" || exit 1


# 9. Execution command mapping directly to venv binary
CMD ["/opt/venv/bin/uvicorn", "rag.api:app", "--host", "0.0.0.0", "--port", "8000"]
