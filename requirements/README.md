Structure: base.in becomes an include fragment only — never compiled on its own.
requirements/
  base.in     # shared direct deps + anyio<4.15   (fragment, not compiled)
  serve.in    # -r base.in ; fastapi, uvicorn[standard], pydantic
  eval.in     # -r base.in ; ragas==0.4.3, mlflow==3.16.0
  corpus.in   # sec-edgar-downloader, beautifulsoup4, lxml
  ingest.in   # -r base.in ; google-cloud-storage — ingestion/Dockerfile image (no fastapi/uvicorn)
  kfp.in      # kfp, kfp-kubernetes — pipeline authoring only (own env, kfp-env); NOT -r base.in, NOT in dev.in
  dev.in      # -r serve.in ; -r eval.in ; -r corpus.in ; pytest, ruff, ipython

rm -f requirements/base.txt
pip-compile requirements/serve.in  -o requirements/serve.txt
pip-compile requirements/eval.in   -o requirements/eval.txt
pip-compile requirements/corpus.in -o requirements/corpus.txt
pip-compile requirements/ingest.in -o requirements/ingest.txt
pip-compile requirements/kfp.in    -o requirements/kfp.txt
pip-compile requirements/dev.in    -o requirements/dev.txt

Each .txt is self-contained (via -r base.in) and resolved independently, so datasets and huggingface_hub negotiate a fsspec they both accept. dev.txt is your real working lock — pip-sync requirements/dev.txt.

If dev.in itself fails to compile later, that's the real signal of an incompatible set to resolve — but your current rag-ops-env has the whole stack installed together already, so a compatible resolution exists.

pip-sync requirements/dev.txt