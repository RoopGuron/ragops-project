import os
from pathlib import Path

from ingestion.gcs_fetch import download_corpus
from ingestion.pipeline import run_ingestion

CORPUS_DEST = "/opt"
PREFIX = "corpus/clean/"

if __name__ == "__main__":
    bucket = os.environ["CORPUS_BUCKET"]
    download_corpus(bucket, PREFIX, CORPUS_DEST)
    os.chdir(CORPUS_DEST)   # manifest paths are cwd-relative; make /opt look like the repo root
    result = run_ingestion(manifest_path=Path(CORPUS_DEST) / "corpus/clean/manifest.jsonl")
    if result["documents"] == 0 :
        raise ValueError("No files ingested")
    else:
      print(f"done: {result}")
