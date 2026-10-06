# tests/test_retriever.py
from rag.retriever import RetrievedChunk, _normalise_item, cap_per_doc


def test_normalise_item_from_doc_id():
    assert _normalise_item("ZS_0001-24-000006_item7a.", "") == "item7a"

def test_normalise_item_falls_back_to_title():
    assert _normalise_item("", "ITEM 1A. Risk Factors") == "item1a"

def test_normalise_item_unknown():
    assert _normalise_item("", "") == "unknown"

def test_normalise_item_from_doc_id_is_case_insensitive():
    # real extracted filenames carry a trailing dot before the extension cut,
    # e.g. "..._item1a.." -> doc_id ends "_item1a." — and uppercase shows up
    # in some manifests too; both must still normalise to lowercase "item7a".
    assert _normalise_item("ZS_0001-24-000007_ITEM7A.", "") == "item7a"

def test_normalise_item_title_fallback_handles_no_space_variant():
    assert _normalise_item("", "ITEM1A") == "item1a"

def _chunk(doc_id: str, idx: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"{doc_id}_c{idx}", text="x", ticker="ZS", fiscal_year=2024,
        item="item1a", doc_id=doc_id, accession="a1", chunk_index=idx, distance=0.1,
    )

def test_cap_per_doc_limits_chunks_per_document():
    chunks = [_chunk("d1", 0), _chunk("d1", 1), _chunk("d1", 2)]
    capped = cap_per_doc(chunks, cap=2)
    assert [c.chunk_id for c in capped] == ["d1_c0", "d1_c1"]

def test_cap_per_doc_preserves_relative_order_across_documents():
    # the diversity cap only matters because the eval set's cross-company
    # questions need chunks from several filings surviving, not just the
    # single closest one — this is the behavior that guarantees that.
    chunks = [_chunk("d1", 0), _chunk("d2", 0), _chunk("d1", 1), _chunk("d1", 2), _chunk("d2", 1)]
    capped = cap_per_doc(chunks, cap=2)
    assert [c.chunk_id for c in capped] == ["d1_c0", "d2_c0", "d1_c1", "d2_c1"]

def test_cap_per_doc_noop_when_under_cap():
    chunks = [_chunk("d1", 0), _chunk("d2", 0)]
    capped = cap_per_doc(chunks, cap=5)
    assert capped == chunks