from ingestion.chunker import chunk_document
from ingestion.loader import Document


def _doc(text, doc_id="ZS_001_item1"):
    return Document(
        doc_id=doc_id, ticker="ZS", accession="0001-24-000006",
        item="ITEM 1. Business", text=text, fiscal_year=2024,
    )

def test_short_text_is_one_chunk():
    chunks = chunk_document(_doc("Hello world."), size=1000, overlap=150)
    assert len(chunks) == 1
    assert chunks[0].text == "Hello world."
    assert chunks[0].chunk_id == "ZS_001_item1_chunk0"
    assert chunks[0].metadata["chunk_index"] == 0

def test_overlap_carries_tail_into_next_chunk():
    text = ("A" * 600) + "\n\n" + ("B" * 600)
    chunks = chunk_document(_doc(text), size=1000, overlap=150)
    assert len(chunks) == 2
    assert chunks[0].text == "A" * 600
    assert chunks[1].text == ("A" * 150) + "\n\n" + ("B" * 600)

def test_oversized_paragraph_hard_cuts_without_overlap():
    chunks = chunk_document(_doc("a" * 2500), size=1000, overlap=0)
    assert [len(c.text) for c in chunks] == [1000, 1000, 500]
    assert "".join(c.text for c in chunks) == "a" * 2500
