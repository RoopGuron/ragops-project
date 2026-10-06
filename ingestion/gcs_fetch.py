"""Stage 0: fetch — download a GCS prefix to local disk so
ingestion/loader.py's manifest-reading stage can run unmodified inside a
KFP pod, where nothing exists locally until this runs.

Only relevant in-cluster: local dev already has corpus/clean/ on disk
(rsync'd to the laptop) and never calls this. Requires GCS read access via
Workload Identity when running in a pod — not wired up yet (see Week 3
resume notes); storage.Client() here relies on Application Default
Credentials being available wherever this runs.
"""


from pathlib import Path

from google.cloud import storage


def download_corpus(bucket_name: str, prefix: str, local_destination: str) -> int:
    """Download every blob under `prefix` in `bucket_name` into
    `local_destination`, recreating the full blob path (including `prefix`)
    underneath it — `local_destination` is the root the bucket gets mirrored
    into, not the target folder itself.

    e.g. download_corpus("ragops-corpus-sec-filings-roop", "corpus/clean/", "/opt")
    writes /opt/corpus/clean/manifest.jsonl. Pass the same local_destination
    through to run_ingestion(manifest_path=Path(local_destination) / "corpus/clean/manifest.jsonl").

    Returns the number of files downloaded. Raises ValueError if none were
    found — a wrong prefix or empty bucket should fail loudly here, not
    surface later as a confusing "no documents" from load_documents().
    """

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)

    # List all blobs matching the prefix (path)
    blobs = bucket.list_blobs(prefix=prefix)

    local_base = Path(local_destination)

    count = 0
    for blob in blobs:
        # Skip if the blob represents a directory placeholder itself
        if blob.name.endswith("/"):
            continue

        # local_destination is the root; prefix's folder structure (corpus/clean/...)
        # is recreated underneath it, not stripped — see docstring above
        relative_path = Path(blob.name)
        local_file_path = local_base / relative_path

        # Create parent directories if they don't exist
        local_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Download the file
        blob.download_to_filename(str(local_file_path))
        print(f"Downloaded: gs://{bucket_name}/{blob.name} -> {local_file_path}")
        count += 1

    if count == 0:
        # The download did not download any files, pls check logs and fix
        raise ValueError(f"No files downloaded from gs://{bucket_name}/{prefix}")
    else:
        print(f"Successfully downloaded {count} files.")

    return count
