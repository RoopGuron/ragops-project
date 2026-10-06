from rag.answer import Citation, parse_citations
from rag.retriever import RetrievedChunk


def _chunk(ticker, fiscal_year, item):
    return RetrievedChunk(
        chunk_id="c1", text="irrelevant", ticker=ticker, fiscal_year=fiscal_year,
        item=item, doc_id="d1", accession="a1", chunk_index=0, distance=0.1,
    )

def test_keeps_a_real_citation():
    chunks = [_chunk("ZS", 2024, "item1a")]
    kept, invented = parse_citations("Risk factors include X [ZS/2024/item1a].", chunks)
    assert kept == [Citation("ZS", 2024, "item1a")]
    assert invented == []

def test_flags_an_invented_citation():
    chunks = [_chunk("ZS", 2024, "item1a")]
    kept, invented = parse_citations("See [WDAY/2023/item7] for details.", chunks)
    assert kept == []
    assert invented == ["WDAY/2023/item7"]

def test_dedupes_repeated_citations():
    chunks = [_chunk("ZS", 2024, "item1a")]
    kept, _ = parse_citations("[ZS/2024/item1a] ... again [ZS/2024/item1a]", chunks)
    assert len(kept) == 1

def test_handles_none_fiscal_year():
    chunks = [_chunk("ZS", None, "item1a")]
    kept, _ = parse_citations("[ZS/None/item1a]", chunks)
    assert kept == [Citation("ZS", None, "item1a")]
