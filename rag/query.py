"""Single-question smoke test for the RAG path — same config the API serves.

    python -m rag.query "How did NVIDIA's export-control risk disclosure change from 2022 to 2024?"

Bulk eval + config sweeps live in evaluation/rag_eval.py
"""

import argparse
import json
import os
from pathlib import Path

from rag.answer import answer_question
from rag.config import RagConfig

_CONFIG_PATH = os.getenv("RAG_CONFIG_PATH", "rag/champion_config.json")
_INFRA_KEYS = {"chroma_host", "chroma_port"}


def _load_config() -> RagConfig:
    try:
        data = json.loads(Path(_CONFIG_PATH).read_text())
    except FileNotFoundError:
        print(f"WARNING: {_CONFIG_PATH} not found; using winning config")
        return RagConfig()
    return RagConfig(**{k: v for k, v in data.items() if k not in _INFRA_KEYS})


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the RAG path one question")
    parser.add_argument("question")
    args = parser.parse_args()

    ans = answer_question(args.question, config=_load_config())
    print(ans.text.strip() or "(empty answer)")
    print("-" * 72)
    print(f"retrieved: {ans.retrieval.get('retrieved', [])}")
    if ans.invented_citations:
        print(f"invented citations: {ans.invented_citations}")


if __name__ == "__main__":
    main()
