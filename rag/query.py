"""CLI for the RAG query path — mirrors `python -m ingestion.pipeline`.

    # one question
    python -m rag.query --question "How did Snowflake's RPO change from 2022 to 2024?"

    # run a whole eval set -> one JSON line per question
    python -m rag.query --eval corpus/eval/qa_eval_set.jsonl --out artifacts/rag_run.jsonl

The --eval output is the hand-off artifact: the Day 2 "answers a handful
correctly" check reads it by eye, and Week 2's Ragas run consumes
{question, answer, contexts, reference_answer} from it. Ragas itself stays
out of this module — this only produces the data it needs. When the eval row
carries expected_sources, each record also gets a recall@k score so retrieval
quality is visible without spending any LLM tokens.
"""

import argparse
from dataclasses import asdict
import json
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
import mlflow
from rag.answer import Answer, answer_question
from rag.config import RagConfig

_DEFAULTS = RagConfig()


def _print_answer(ans: Answer) -> None:
    print("\n" + "=" * 72)
    print(f"Q: {ans.question}")
    print("=" * 72)
    print(ans.text.strip() or "(empty answer)")
    print("-" * 72)
    print(f"retrieved ({ans.retrieval.get('n_retrieved', 0)}):")
    for sel, dist in zip(ans.retrieval.get("retrieved", []), ans.retrieval.get("distances", [])):
        print(f"  {dist:<8} {sel}")
    if ans.invented_citations:
        print(f"invented citations (not retrieved): {ans.invented_citations}")
    if ans.usage:
        print(f"tokens: {ans.usage}")


def _to_record(ans: Answer, eval_row: dict | None) -> dict:
    rec = {
        "question": ans.question,
        "answer": ans.text,
        "citations": [str(c) for c in ans.citations],
        "invented_citations": ans.invented_citations,
        "retrieved": ans.retrieval.get("retrieved", []),
        "distances": ans.retrieval.get("distances", []),
        "model": ans.model,
        "usage": ans.usage,
        "contexts": [c.text for c in ans.contexts],
    }
    if eval_row:
        rec["id"] = eval_row.get("id")
        rec["type"] = eval_row.get("type")
        rec["expected_sources"] = eval_row.get("expected_sources", [])
        rec["reference_answer"] = eval_row.get("reference_answer")
        expected = set(eval_row.get("expected_sources", []))
        print(f"  expected sources: {expected}")
        if expected:
            hit = expected & set(rec["retrieved"])
            print(f"  retrieved sources: {set(rec['retrieved'])}")
            print(f"  hit sources: {hit}")
            rec["recall_at_k"] = round(len(hit) / len(expected), 3)
    return rec


def _build_where(row: dict) -> dict | None:
    """Turn an eval row's companies/filing_years into a Chroma metadata filter.

    Chroma keys off the stored metadata field names (ticker, fiscal_year), needs
    operator syntax ($in for membership), and allows exactly one top-level key —
    so multiple conditions get wrapped in $and. Empty lists -> no filter, which
    is what neg-01 (unanswerable) wants.
    """
    conds = []
    if row.get("companies"):
        conds.append({"ticker": {"$in": row["companies"]}})
    if row.get("filing_years"):
        conds.append({"fiscal_year": {"$in": row["filing_years"]}})
    if not conds:
        return None
    return conds[0] if len(conds) == 1 else {"$and": conds}


@contextmanager
def _tracked_run(config: RagConfig):
    mlflow.set_experiment("RAG_Optimization_Engine")
    with mlflow.start_run() as run:
        mlflow.log_params(asdict(config))
        print(f"Tracking run under ID: {run.info.run_id}")

        # Start the timer immediately before yielding control
        start_time = time.perf_counter()

        try:
          yield run

        except Exception as e:
            mlflow.set_tag("error_message", str(e))
            mlflow.log_text(traceback.format_exc(), "error_traceback.txt")
            raise e
            
        finally:
            # This block ALWAYS runs, even if an exception was raised above
            end_time = time.perf_counter()
            duration_seconds = end_time - start_time
            
            # Log the total time as a metric in MLflow
            mlflow.log_metric("execution_time_seconds", duration_seconds)
            print(f"Run completed in {duration_seconds:.2f} seconds.")


def run_question(question: str, config: RagConfig) -> None:
    with _tracked_run(config):
        ans = answer_question(question, config=config, where=None)
        _print_answer(ans)
        mlflow.log_metric("n_invented_citations", len(ans.invented_citations))


def run_eval(path: Path, out: Path | None, config: RagConfig) -> None:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    print(f"loaded {len(rows)} eval questions from {path}")

    with _tracked_run(config):
        records, recalls = [], []
        for row in rows:
            print(f"\n=== {row.get('id', '?')} === {row.get('question', '(no question)')} === {row.get('expected_sources', [])}")
            ans = answer_question(row["question"], config=config, where=_build_where(row))
            rec = _to_record(ans, row)
            records.append(rec)
            if "recall_at_k" in rec:
                recalls.append(rec["recall_at_k"])
            print(
                f"  [{rec.get('id', '?')}] recall@{config.top_k}={rec.get('recall_at_k', 'n/a')} "
                f"citations={rec['citations']}"
            )

        if recalls:
            mlflow.log_metric("mean_recall", sum(recalls) / len(recalls))
            print(f"\nmean recall@{config.top_k}: {sum(recalls) / len(recalls):.3f} "
                  f"over {len(recalls)} scored rows")

        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w") as f:
                for rec in records:
                    f.write(json.dumps(rec) + "\n")
            print(f"wrote {len(records)} records to {out}")
            mlflow.log_artifact(str(out))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the RAG query path")
    parser.add_argument("--question", help="a single question to answer")
    parser.add_argument("--eval", type=Path, help="path to a qa_eval_set.jsonl to run in bulk")
    parser.add_argument("--out", type=Path, help="write --eval results here (JSONL)")
    parser.add_argument("--top-k", type=int, default=_DEFAULTS.top_k)
    parser.add_argument("--per-doc-cap", type=int, default=_DEFAULTS.per_doc_cap)
    parser.add_argument("--model", default=_DEFAULTS.llm_model, help="LLM model id")
    parser.add_argument("--chroma-host", default=_DEFAULTS.chroma_host)
    parser.add_argument("--chroma-port", type=int, default=_DEFAULTS.chroma_port)
    args = parser.parse_args()

    config = RagConfig(
        chroma_host=args.chroma_host,
        chroma_port=args.chroma_port,
        top_k=args.top_k,
        per_doc_cap=args.per_doc_cap,
        llm_model=args.model,
    )

    if args.eval:
        run_eval(args.eval, args.out, config)
    elif args.question:
        run_question(args.question, config)
    else:
        parser.error("pass --question or --eval")


if __name__ == "__main__":
    main()
