"""
RAGOps corpus builder — pulls ~300 SEC 10-K filings via EDGAR.

Design choice: one sector (software/cloud), ~50 tickers x ~6 fiscal years
= ~300 filings. Same-sector filings give real topical overlap (so retrieval
has to discriminate between similar-but-different risk-factor language
across companies), while the multi-year span per company supports
"how has X changed over time" eval questions. Adjust TICKERS/date range
to widen or narrow the corpus.

Two stages:
  1) download_filings()  — pulls raw filings via sec-edgar-downloader
  2) extract_items()     — slices each filing down to the narratively
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

from sec_edgar_downloader import Downloader

# ---- config ---------------------------------------------------------------

# SEC requires a real company/app name + contact email in the User-Agent.
# Generic or missing values get you rate-limited or blocked outright.
COMPANY_NAME = "RAGOpsPortfolioProject"
CONTACT_EMAIL = "rguron@gmail.com"

RAW_DIR = Path("./corpus/raw")
CLEAN_DIR = Path("./corpus/clean")

# ~50 software/cloud tickers -> ~6 fiscal years each ≈ 300 filings.
# Swap this list for whatever sector/theme you want the corpus to live in.
TICKERS = [
    "MSFT", "ORCL", "CRM", "ADBE", "INTU", "NOW", "WDAY", "SNOW", "DDOG",
    "PANW", "CRWD", "ZS", "OKTA", "NET", "MDB", "TEAM", "HUBS", "TWLO",
    "DOCU", "ZM", "SPLK", "FTNT", "VEEV", "PAYC", "PCTY", "BILL", "PATH",
    "GTLB", "S", "ESTC", "FROG", "PD", "BOX", "DBX", "SMAR", "APPF",
    "BLKB", "DT", "FSLY", "AI", "CFLT", "ASAN", "MNDY", "FIVN", "RNG",
    "SUMO", "PLTR", "U", "COUP", "NEWR",
]

FORM = "10-K"
AFTER = "2019-01-01"
BEFORE = "2025-01-01"

# Only these Items get kept — the narrative sections that actually make
# good retrieval/eval material. Everything else (cover page, signatures,
# exhibit index, XBRL, raw financial statements) gets dropped.
ITEM_PATTERN = re.compile(
    r"item\s+(1|1a|7|7a)\.?\s+",
    re.IGNORECASE,
)
ITEM_LABELS = {
    "1": "Item 1 - Business",
    "1a": "Item 1A - Risk Factors",
    "7": "Item 7 - MD&A",
    "7a": "Item 7A - Quantitative and Qualitative Disclosures About Market Risk",
}


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


# ---- stage 2: extract narrative Items --------------------------------------

def extract_items():
    from bs4 import BeautifulSoup

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []

    for filing_dir in RAW_DIR.glob(f"sec-edgar-filings/*/{FORM}/*"):
        ticker = filing_dir.parts[-3]
        accession = filing_dir.name

        primary_doc = next(filing_dir.glob("*.htm"), None)
        if primary_doc is None:
            continue

        html = primary_doc.read_text(errors="ignore")
        text = BeautifulSoup(html, "lxml").get_text("\n")

        # Split on "Item N." headers, keep only the Items we care about.
        pieces = ITEM_PATTERN.split(text)
        # pieces alternates [preamble, item_key, item_text, item_key, item_text, ...]
        for i in range(1, len(pieces), 2):
            key = pieces[i].lower()
            body = pieces[i + 1].strip() if i + 1 < len(pieces) else ""
            if key not in ITEM_LABELS or len(body) < 500:
                continue

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

    (CLEAN_DIR / "manifest.jsonl").write_text(
        "\n".join(json.dumps(m) for m in manifest)
    )
    print(f"Extracted {len(manifest)} Item sections -> {CLEAN_DIR}/manifest.jsonl")


if __name__ == "__main__":
    download_filings()
    extract_items()
