# RAG eval set — SEC 10-K corpus

`qa_eval_set.jsonl` — 25 questions for evaluating the RAG query path (retrieval + generation)
against the corpus in `corpus/clean/`. One JSON object per line.

## Why these questions

The corpus is a longitudinal panel: ~47 SaaS/cloud/infra companies, each with Item 1 / 1A / 7 / 7A
across ~2019–2025. The two things that structure is good for are the two question types that
dominate the set:

| type | count | tests |
|------|-------|-------|
| `within_company_over_time` | 10 | retrieval must pull the *same* company across *different* filing years and the answer must compare them |
| `cross_company_same_year` | 10 | retrieval must pull *different* companies for the *same* year and the answer must contrast them |
| `single_doc` | 4 | floor case — one filing, one item; easy retrieval, checks grounding |
| `unanswerable` | 1 | faithfulness — target is not in the corpus; system should decline, not fabricate |

## Fields

| field | meaning |
|-------|---------|
| `id` | stable id (`wct-*`, `ccy-*`, `sd-*`, `neg-*`) |
| `type` | one of the four above |
| `question` | the user query |
| `companies` | tickers involved (`[]` for `unanswerable`) |
| `filing_years` | **year the 10-K was filed**, matching `_fiscal_year_from_accession` in `ingestion/loader.py` — see caveat below |
| `items` | which extracted items the answer should draw on (`item1`/`item1a`/`item7`/`item7a`) |
| `expected_sources` | retrieval gold, as `TICKER/filing_year/item` selectors — score retrieval (recall@k, MRR) against the chunks whose metadata matches these |
| `reference_answer` | drafted from domain knowledge of these filings; qualitative claims are usable as-is, anything numeric is a sketch |
| `needs_numeric_verification` | `true` where `reference_answer` contains figures (growth rates, TAM, RPO, segment mix, sensitivities) that must be read out of the retrieved chunks before the reference is locked |

## Filing-year vs fiscal-year caveat

`filing_years` is the year the 10-K was *filed*, not the period it covers. For companies with
non-December fiscal year-ends this lags by up to a year — e.g. a Salesforce 10-K filed in 2025
covers FY2025 ended Jan 31 2025; an NVIDIA 10-K filed in Feb 2022 covers the year ended Jan 2022.
Affected here: CRM, ADBE, MSFT, NVDA, ZM, WDAY, NOW. The questions are written so the filing-year
label is unambiguous; keep this in mind if you rephrase any question in terms of "fiscal YYYY".

## Workflow

1. Run the RAG path over each `question`.
2. Retrieval eval: compare returned chunk metadata to `expected_sources`.
3. Before locking `reference_answer` on rows with `needs_numeric_verification: true`, read the
   gold chunks and fill in the real figures.
4. Generation eval (week 2): feed `question` / generated answer / retrieved `contexts` /
   `reference_answer` to Ragas (faithfulness, answer relevancy, context precision). `neg-01`
   should yield a refusal / "no relevant context" response.
