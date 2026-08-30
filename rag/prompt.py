"""Stage 2: turn a question + retrieved chunks into (system, user) prompt text.

Pure functions, no network — unit-testable on fake chunks. The template body
lives in rag/prompts/<version>.txt with a VERSION constant so Week 2's MLflow
comparison can track "prompt template" as a real, named param instead of an
inline string that quietly drifts.

The system prompt carries the grounding contract: answer only from context,
cite every claim as [TICKER/filing_year/itemX], and decline explicitly when
the context doesn't cover the question. That decline clause is what makes the
eval set's neg-01 row refuse instead of fabricating, and what Ragas
faithfulness keys on in Week 2.
"""

from pathlib import Path

from rag.retriever import RetrievedChunk

VERSION = "answer_v1"

_PROMPT_DIR = Path(__file__).parent / "prompts"

_ITEM_LABELS = {
    "item1": "Item 1 (Business)",
    "item1a": "Item 1A (Risk Factors)",
    "item7": "Item 7 (MD&A)",
    "item7a": "Item 7A (Market Risk)",
}

SYSTEM = (
    "You are a financial-filings analyst. You answer questions about SEC 10-K "
    "filings using ONLY the numbered context passages provided by the user.\n\n"
    "Rules:\n"
    "1. Ground every factual claim in the context. Immediately after each claim, "
    "cite its source in square brackets exactly as written in that passage's "
    "header, e.g. [SNOW/2024/item7].\n"
    "2. If the context does not contain enough information to answer, say so "
    'explicitly: "The provided filings do not contain information about ...". '
    "Never fall back on knowledge from outside the context.\n"
    "3. For comparison questions, only compare the companies or years actually "
    "present in the context. If one side is missing, say which is missing "
    "rather than guessing it.\n"
    "4. End with a line `Sources:` followed by the list of "
    "[TICKER/filing_year/item] selectors you cited."
)


def _load_template(version: str) -> str:
    return (_PROMPT_DIR / f"{version}.txt").read_text()


def _item_label(item: str) -> str:
    return _ITEM_LABELS.get(item, item)


def format_context(chunks: list[RetrievedChunk], max_chars: int | None = None) -> str:
    """Numbered context blocks, each headed by the metadata needed to cite it."""
    blocks: list[str] = []
    total = 0
    for i, c in enumerate(chunks, start=1):
        header = (
            f"[{i}] {c.ticker} - filed {c.fiscal_year} - {_item_label(c.item)}"
            f"  |  cite as [{c.selector}]"
        )
        block = f"{header}\n{c.text.strip()}"
        if max_chars is not None and blocks and total + len(block) > max_chars:
            break
        blocks.append(block)
        total += len(block)
    return "\n\n".join(blocks)


def build_prompt(
    question: str,
    chunks: list[RetrievedChunk],
    *,
    version: str = VERSION,
    max_context_chars: int | None = None,
) -> tuple[str, str]:
    context = format_context(chunks, max_chars=max_context_chars)
    # str.replace, not str.format — 10-K text can contain literal braces.
    user = (
        _load_template(version)
        .replace("{context}", context)
        .replace("{question}", question)
    )
    return SYSTEM, user
