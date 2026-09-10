"""Single-question smoke test for the RAG path — same config the API serves.

    python -m rag.query "How did NVIDIA's export-control risk disclosure change from 2022 to 2024?"

Bulk eval + config sweeps live in evaluation/generate.py
"""

import argparse

from rag.answer import answer_question
from rag.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the RAG path one question")
    parser.add_argument("question")
    args = parser.parse_args()

    ans = answer_question(args.question, config= load_config())
    print(ans.text.strip() or "(empty answer)")
    print("-" * 72)
    print(f"retrieved: {ans.retrieval.get('retrieved', [])}")
    if ans.invented_citations:
        print(f"invented citations: {ans.invented_citations}")


if __name__ == "__main__":
    main()
