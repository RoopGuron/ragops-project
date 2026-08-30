"""
RAGOps corpus builder — pulls ~300 SEC 10-K filings via EDGAR.

Design choice: one sector (software/cloud), ~50 tickers x ~6 fiscal years
= ~300 filings. Same-sector filings give real topical overlap (so retrieval
has to discriminate between similar-but-different risk-factor language
across companies), while the multi-year span per company supports
"how has X changed over time" eval questions. Adjust TICKERS/date range
to widen or narrow the corpus.

Three stages:
  1) download_filings()  — pulls raw filings via sec-edgar-downloader
  2) cleanup_raw()       — deletes full-submission.txt per filing once its
                            primary-document.html is confirmed present.
                            sec-edgar-downloader saves both; the full
                            submission (all exhibits + XBRL instance docs
                            in one SGML blob) runs ~15-25MB per filing vs
                            ~3-4MB for the primary document, and nothing
                            downstream reads it — it's ~80% of the raw
                            footprint for zero benefit. Run this before
                            extract_items(), not just at the end, so the
                            corpus doesn't peak at multiple GB unnecessarily
                            while you're still pulling tickers.
  3) extract_items()     — slices each filing down to the narratively
                            rich Items (Business, Risk Factors, MD&A)
                            instead of ingesting the whole document,
                            which is mostly boilerplate, exhibit indexes,
                            and financial tables that don't chunk well
                            for embedding-based retrieval.

Run:
    pip install -U sec-edgar-downloader beautifulsoup4 lxml
    python pull_10k_corpus.py
"""

import json
import re
import time
from pathlib import Path
import unicodedata
import argparse

from sec_edgar_downloader import Downloader

# ---- config ---------------------------------------------------------------

# SEC requires a real company/app name + contact email in the User-Agent.
# Generic or missing values get you rate-limited or blocked outright.
COMPANY_NAME = "RAGOpsPortfolioProject"
CONTACT_EMAIL = "rguron@gmail.com"

RAW_DIR = Path("./corpus/raw")
CLEAN_DIR = Path("./corpus/clean")
DEBUG_DIR = Path("./corpus/debug")

# ~50 software/cloud tickers -> ~6 fiscal years each ≈ 300 filings.
# Swap this list for whatever sector/theme you want the corpus to live in.
TICKERS = [
    "MSFT", "ORCL", "CRM", "ADBE", "INTU", "NOW", "WDAY", "SNOW", "DDOG",
    "PANW", "CRWD", "ZS", "OKTA", "NET", "MDB", "TEAM", "HUBS", "TWLO",
    "DOCU", "ZM", "EPAM", "FTNT", "VEEV", "PAYC", "PCTY", "BILL", "PATH",
    "GTLB", "S", "ESTC", "FROG", "PD", "BOX", "DBX", "NAVN", "APPF",
    "BLKB", "DT", "FSLY", "AI", "TSLA", "ASAN", "MNDY", "FIVN", "RNG",
    "AVGO", "PLTR", "U", "GOOG", "NVDA",
]

FORM = "10-K"
AFTER = "2019-01-01"
BEFORE = "2026-01-01"

# Only these Items get kept — the narrative sections that actually make
# good retrieval/eval material. Everything else (cover page, signatures,
# exhibit index, XBRL, raw financial statements) gets dropped.
#
# NOTE: matching "item 1a" *anywhere* in the text (original approach) badly
# over-matches. 10-Ks are full of casual cross-references — "as discussed in
# Item 7 above", "see Item 1A, Risk Factors" — sprinkled throughout the prose,
# on top of the real section headers and a table-of-contents listing at the
# top. A naive split on every occurrence treats each cross-reference as a new
# section boundary, so the same content gets captured multiple times and the
# "extracted" text ends up *larger* than the source HTML — which is exactly
# the size anomaly that surfaced this bug. Anchoring to whole, short,
# standalone lines (real headers) and taking the *last* such match per item
# (the ToC mention comes first, the real section header comes later) fixes it.
# Match the item token generically (\d+[a-z]?) rather than alternating over
# "1a|1|7a|7" literally — a literal alternation lets "1" match as a prefix of
# "16", "10"-"15", "1B", "1C", etc. (regex has no built-in notion that "1" and
# "16" are different item numbers), which is how a real filing's Part III/IV
# section ("Item 16. Form 10-K Summary") got mistaken for "Item 1" during
# validation against a real ADBE filing. Capturing the full token and then
# checking it against ITEM_LABELS closes that off correctly.
HEADER_RE = re.compile(r"^item\s+(\d+[a-z]?\.)\s*[-–—:]?\s*(.*)$", re.IGNORECASE)
MAX_HEADER_LINE_LEN = 120  # real headers are short lines; cross-refs sit inside long sentences

ITEM_LABELS = {
    "1.": "ITEM 1. BUSINESS",
    "1a.": "ITEM 1A. Risk Factors",
    "7.": "ITEM 7. MANAGEMENT&#8217;s DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS",
    "7a.": "ITEM 7A. Quantitative and Qualitative Disclosures About Market Risk",
}


def find_all_headers(lines):
    """Return {item_key: line_index} for the *last* short standalone-line
    match of every Item-like header found — Item 1 through Item 16, not just
    the four we keep. Skips the table-of-contents occurrence (which comes
    first) and inline cross-references (which aren't short standalone lines)
    and lands on each real section header instead.

    Finding *all* headers, not just the four tracked ones, matters for where
    each kept section ends: without a header for Item 8 to stop at, Item 7A's
    body has nothing marking its end and runs on into Financial Statements,
    Part III governance disclosures, the exhibit index, and signatures —
    all real 10-K content, just not what "Item 7A" means. Every item acts as
    a boundary; only ITEM_LABELS keys get written out in extract_items().
    """
    last_seen = {}
    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line or len(line) > MAX_HEADER_LINE_LEN:
            continue
        m = HEADER_RE.match(line)
        if m:
            key = m.group(1).lower()
            last_seen[key] = idx  # overwrite each time -> ends on the last match
    return last_seen


# ---- stage 1: download ------------------------------------------------------
def download_filings():
    dl = Downloader(COMPANY_NAME, CONTACT_EMAIL, download_folder=RAW_DIR)

    for ticker in TICKERS:
        try:
            # download_details=True also pulls the human-readable primary
            # document, not just the raw submission text file.
            n = dl.get(
                FORM,
                ticker,
                after=AFTER,
                before=BEFORE,
                download_details=True,
            )
            print(f"{ticker}: downloaded {n} filings")
        except Exception as e:
            # A handful of tickers will fail (delisted, renamed, no filings
            # in range) — log and move on rather than aborting the run.
            print(f"{ticker}: FAILED — {e}")

        # sec-edgar-downloader already paces requests, but stay well under
        # the SEC's 10 req/sec ceiling if you add any custom calls here.
        time.sleep(0.2)


# ---- stage 2: drop the giant full-submission.txt we never read -------------
def cleanup_raw():
    freed = 0
    kept, dropped = 0, 0
    for filing_dir in RAW_DIR.glob(f"sec-edgar-filings/*/{FORM}/*"):
        primary = filing_dir / "primary-document.html"
        full_sub = filing_dir / "full-submission.txt"
        if primary.exists() and full_sub.exists():
            freed += full_sub.stat().st_size
            full_sub.unlink()
            dropped += 1
        else:
            kept += 1  # no primary doc found yet — leave full-submission.txt as a fallback

    print(f"cleanup_raw: removed {dropped} full-submission.txt files "
          f"({freed / 1e9:.2f} GB freed), kept {kept} filings without a primary doc")


# ---- stage 3: extract narrative Items --------------------------------------
def extract_items(debug=False):
    from bs4 import BeautifulSoup

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []

    for filing_dir in RAW_DIR.glob(f"sec-edgar-filings/*/{FORM}/*"):
        ticker = filing_dir.parts[-3]
        accession = filing_dir.name

        # sec-edgar-downloader names this file "primary-document.html" —
        # note the .html, not .htm. A "*.htm" glob (an earlier version of
        # this script used one) silently matches nothing here and every
        # filing gets skipped with no error, so target the real filename.
        primary_doc = filing_dir / "primary-document.html"
        if not primary_doc.exists():
            continue

        html = primary_doc.read_text(errors="ignore")
        html_bytes = len(html.encode("utf-8"))
        text = BeautifulSoup(html, "lxml").get_text("\n")
        clean_text = unicodedata.normalize("NFKD", text)
        # Write out the cleaned text for inspection/debugging, but don't ingest it 
        if debug:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            with open(f"./corpus/debug/{ticker}_{accession}.txt", "w") as file:
                file.write(clean_text)

        lines = clean_text.split("\n")

        headers = find_all_headers(lines)
        if not headers:
            continue

        # Walk *every* header in document order so each kept item's body
        # stops at the next real section, whatever it is — not just at the
        # next kept item — then filter down to ITEM_LABELS for output.
        ordered = sorted(headers.items(), key=lambda kv: kv[1])
        total_extracted = 0
        for pos, (key, start_idx) in enumerate(ordered):
            if key not in ITEM_LABELS:
                continue
            end_idx = ordered[pos + 1][1] if pos + 1 < len(ordered) else len(lines)
            body = "\n".join(lines[start_idx + 1:end_idx]).strip()
            if len(body) < 500:
                continue
            total_extracted += len(body)

            doc_id = f"{ticker}_{accession}_item{key}"
            out_path = CLEAN_DIR / f"{doc_id}.txt"
            out_path.write_text(body)

            manifest.append({
                "doc_id": doc_id,
                "ticker": ticker,
                "accession": accession,
                "item": ITEM_LABELS[key],
                "path": str(out_path),
                "chars": len(body),
            })

        # Sanity check: extracted text (all tracked items combined) should
        # never exceed the source HTML's byte size — HTML markup only adds
        # bytes, it never removes them. If this fires, headers are still
        # being over-matched (e.g. an unusually formatted filing) and the
        # output for this filing needs a manual look before it's trusted.
        if total_extracted > html_bytes:
            print(
                f"WARNING: {ticker} {accession} — extracted {total_extracted} chars "
                f"from a {html_bytes}-byte source file. Likely duplicate/overlapping "
                f"matches; inspect this filing's output manually before ingesting it."
            )

    (CLEAN_DIR / "manifest.jsonl").write_text(
        "\n".join(json.dumps(m) for m in manifest)
    )
    print(f"Extracted {len(manifest)} Item sections -> {CLEAN_DIR}/manifest.jsonl")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pull 10-K filings from SEC EDGAR, clean them, and extract narrative Items. --- Run in Debug Mode"
    )
    # Defaults to False, turns True if --debug is passed
    parser.add_argument("--debug", help = "Run in debug mode, saving cleaned text for inspection", action="store_true")
    args = parser.parse_args()
    print(f"Debug mode: {args.debug}")

    download_filings()
    cleanup_raw()
    extract_items(args.debug)
