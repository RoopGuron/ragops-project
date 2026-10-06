import argparse
import os

import kfp

from pipelines.rag_pipeline import rag_pipeline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    args = parser.parse_args()


    sha = os.environ["GITHUB_SHA"]
    os.environ["INGEST_IMAGE"] = f"ghcr.io/roopguron/ragops-ingestion:{sha}"
    os.environ["EVAL_IMAGE"] = f"ghcr.io/roopguron/ragops-evaluation:{sha}"

    client = kfp.Client(host=args.host)
    run = client.create_run_from_pipeline_func(
        rag_pipeline, experiment_name="ci-dev", run_name=f"ci-{sha[:8]}",
    )
    print(f"Submitted run {run.run_id} for commit {sha}")
    print(f"KFP UI: {args.host}/#/runs/details/{run.run_id}")

if __name__ == "__main__":
    main()

