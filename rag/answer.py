"""Orchestrator: question -> retrieve -> prompt -> generate -> Answer.

Ties the three stages together and does citation post-processing: the model's
[TICKER/year/item] tokens are parsed back out and intersected with what was
actually retrieved. A citation the model invented — one whose selector was
never in the context — is dropped from `citations` and recorded separately in
`invented_citations`, since it's a faithfulness miss worth seeing.

The raw retrieved chunks ride through untouched on Answer.contexts — Week 2's
Ragas run needs them as `contexts` alongside the question and answer.
"""

import re
from dataclasses import dataclass, field

from rag.config import RagConfig
from rag.generator import generate
from rag.prompt import build_prompt
from rag.retriever import RetrievedChunk, cap_per_doc, retrieve


@dataclass
class Citation:
    ticker: str
    fiscal_year: int | None
    item: str

    def __str__(self) -> str:
        return f"{self.ticker}/{self.fiscal_year}/{self.item}"


@dataclass
class Answer:
    question: str
    text: str
    citations: list[Citation] = field(default_factory=list)
    contexts: list[RetrievedChunk] = field(default_factory=list)
    model: str = ""
    usage: dict = field(default_factory=dict)
    retrieval: dict = field(default_factory=dict)
    invented_citations: list[str] = field(default_factory=list)


_CITATION_RE = re.compile(
    r"\[\s*([A-Za-z0-9.\-]+)\s*/\s*(\d{4}|None)\s*/\s*(item\d+[a-z]?)\s*\]",
    re.IGNORECASE,
)

_NO_CONTEXT_MSG = "No relevant context was found in the filing corpus for this question."


def parse_citations(
    text: str, chunks: list[RetrievedChunk]
) -> tuple[list[Citation], list[str]]:
    retrieved = {c.selector for c in chunks}
    kept: list[Citation] = []
    invented: list[str] = []
    seen: set[str] = set()
    for tk, yr, item in _CITATION_RE.findall(text):
        selector = f"{tk.upper()}/{yr}/{item.lower()}"
        if selector in seen:
            continue
        seen.add(selector)
        if selector in retrieved:
            fy = None if yr == "None" else int(yr)
            kept.append(Citation(tk.upper(), fy, item.lower()))
        else:
            invented.append(selector)
    return kept, invented


def answer_question(question: str, *, config: RagConfig | None = None, where: dict | None = None) -> Answer:
    config = config or RagConfig()

    chunks = retrieve(
        question,
        top_k=config.top_k,
        where=where,
        host=config.chroma_host,
        port=config.chroma_port,
        collection_name=config.collection_name,
        embedding_model=config.embedding_model,
    )
    if config.per_doc_cap:
        chunks = cap_per_doc(chunks, config.per_doc_cap)

    if not chunks:
        return Answer(
            question=question,
            text=_NO_CONTEXT_MSG,
            model=config.llm_model,
            retrieval={"top_k": config.top_k, "n_retrieved": 0, "retrieved": [], "distances": []},
        )

    system, user = build_prompt(
        question, chunks, version=config.prompt_version, max_context_chars=config.max_context_chars
    )
    gen = generate(system, user, model=config.llm_model, max_tokens=config.max_tokens)

    citations, invented = parse_citations(gen.text, chunks)
    print(f" chunks retrieved: {len(chunks)}, citations kept: {len(citations)}, citations invented: {len(invented)} ")
    print(f"  retrieved chunks: {[c.selector for c in chunks]}")
    print(f"  retrieved citations: {[str(c) for c in citations]}")
    print(f"  invented citations: {invented}")
    return Answer(
        question=question,
        text=gen.text,
        citations=citations,
        contexts=chunks,
        model=gen.model,
        usage=gen.usage,
        retrieval={
            "top_k": config.top_k,
            "per_doc_cap": config.per_doc_cap,
            "n_retrieved": len(chunks),
            "retrieved": [c.selector for c in chunks],
            "distances": [round(c.distance, 4) for c in chunks],
        },
        invented_citations=invented,
    )
