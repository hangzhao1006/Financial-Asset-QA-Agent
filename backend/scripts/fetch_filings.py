"""SEC EDGAR filing fetcher for RAG ingestion.

This script complements fetch_reports.py:
- fetch_reports.py is manifest-driven and supports official PDF/HTML + EDGAR.
- fetch_filings.py is CLI-driven and focused on ad-hoc SEC 10-K / 10-Q pulls.

Usage:
    python -m backend.scripts.fetch_filings --ticker TSLA --type 10-K --count 2
    python -m backend.scripts.fetch_filings --ticker AAPL --type 10-Q --list-only
    python -m backend.scripts.fetch_filings --all --type 10-K
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from html import unescape
from pathlib import Path

import httpx

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "FinQ demo contact@example.com")
SEC_TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
OUTPUT_DIR = _PROJECT_ROOT / "knowledge_base" / "filings"

DEFAULT_COMPANIES = [
    {"ticker": "TSLA", "name": "Tesla"},
    {"ticker": "AAPL", "name": "Apple"},
    {"ticker": "BABA", "name": "Alibaba"},
    {"ticker": "GOOGL", "name": "Alphabet/Google"},
    {"ticker": "MSFT", "name": "Microsoft"},
    {"ticker": "NVDA", "name": "NVIDIA"},
    {"ticker": "AMZN", "name": "Amazon"},
    {"ticker": "META", "name": "Meta"},
]

_CIK_CACHE: dict[str, str] = {}


@dataclass
class FilingInfo:
    ticker: str
    company_name: str
    filing_type: str
    filing_date: str
    report_date: str
    accession_number: str
    filing_url: str
    index_url: str
    primary_document: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch SEC EDGAR filings into Markdown files.")
    parser.add_argument("--ticker", type=str, help="Stock ticker, e.g. TSLA")
    parser.add_argument("--type", default="10-K", choices=["10-K", "10-Q"], help="Filing type.")
    parser.add_argument("--count", type=int, default=2, help="Number of recent filings to fetch.")
    parser.add_argument("--all", action="store_true", help="Fetch for all default companies.")
    parser.add_argument("--list-only", action="store_true", help="Only list filing URLs, do not download.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Markdown output directory.")
    parser.add_argument("--max-chars", type=int, default=180_000, help="Maximum filing text chars to keep.")
    parser.add_argument("--sec-user-agent", default=SEC_USER_AGENT, help="SEC EDGAR User-Agent header.")
    args = parser.parse_args()

    if args.all:
        fetch_all_default(
            filing_type=args.type,
            count=args.count,
            list_only=args.list_only,
            output_dir=Path(args.output_dir),
            max_chars=args.max_chars,
            sec_user_agent=args.sec_user_agent,
        )
    elif args.ticker:
        fetch_and_save(
            ticker=args.ticker,
            filing_type=args.type,
            count=args.count,
            list_only=args.list_only,
            output_dir=Path(args.output_dir),
            max_chars=args.max_chars,
            sec_user_agent=args.sec_user_agent,
        )
    else:
        parser.print_help()


def fetch_all_default(
    filing_type: str = "10-K",
    count: int = 1,
    list_only: bool = False,
    output_dir: Path = OUTPUT_DIR,
    max_chars: int = 180_000,
    sec_user_agent: str = SEC_USER_AGENT,
) -> list[Path]:
    all_files: list[Path] = []
    for company in DEFAULT_COMPANIES:
        logger.info("=" * 72)
        logger.info("Fetching %s for %s (%s)", filing_type, company["name"], company["ticker"])
        files = fetch_and_save(
            ticker=company["ticker"],
            filing_type=filing_type,
            count=count,
            list_only=list_only,
            output_dir=output_dir,
            max_chars=max_chars,
            sec_user_agent=sec_user_agent,
        )
        all_files.extend(files)
        time.sleep(0.5)

    logger.info("Done. Saved %d filing document(s) to %s", len(all_files), output_dir)
    if all_files:
        logger.info("Next: python -m backend.scripts.ingest_knowledge_base")
    return all_files


def fetch_and_save(
    ticker: str,
    filing_type: str = "10-K",
    count: int = 2,
    list_only: bool = False,
    output_dir: Path = OUTPUT_DIR,
    max_chars: int = 180_000,
    sec_user_agent: str = SEC_USER_AGENT,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    with _get_client(sec_user_agent) as client:
        filings = search_filings(ticker=ticker, filing_type=filing_type, count=count, client=client)
        if not filings:
            logger.warning("No %s filings found for %s", filing_type, ticker)
            return []

        for filing in filings:
            logger.info("[%s] %s %s - %s", filing.ticker, filing.filing_type, filing.filing_date, filing.filing_url)
            if list_only:
                continue

            text = fetch_filing_text(filing.filing_url, client=client, max_chars=max_chars)
            if not text:
                logger.warning("Empty filing text for %s %s", filing.ticker, filing.accession_number)
                continue

            sections = extract_key_sections(text)
            path = save_filing_markdown(filing, text, sections, output_dir)
            saved.append(path)
            time.sleep(0.3)

    return saved


def _get_client(sec_user_agent: str) -> httpx.Client:
    return httpx.Client(
        headers={
            "User-Agent": sec_user_agent,
            "Accept-Encoding": "gzip, deflate",
        },
        timeout=45.0,
        follow_redirects=True,
    )


def resolve_cik(ticker: str, client: httpx.Client) -> str | None:
    ticker_upper = ticker.upper()
    if ticker_upper in _CIK_CACHE:
        return _CIK_CACHE[ticker_upper]

    try:
        response = client.get(SEC_TICKER_CIK_URL)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        logger.error("Failed to fetch SEC ticker CIK mapping: %s", exc)
        return None

    for entry in data.values():
        entry_ticker = str(entry.get("ticker", "")).upper()
        cik = str(entry.get("cik_str", "")).zfill(10)
        if entry_ticker and cik:
            _CIK_CACHE[entry_ticker] = cik

    return _CIK_CACHE.get(ticker_upper)


def search_filings(
    ticker: str,
    filing_type: str = "10-K",
    count: int = 4,
    client: httpx.Client | None = None,
) -> list[FilingInfo]:
    own_client = client is None
    if client is None:
        client = _get_client(SEC_USER_AGENT)

    try:
        cik = resolve_cik(ticker, client)
        if not cik:
            logger.warning("Could not resolve SEC CIK for %s", ticker)
            return []

        try:
            response = client.get(SEC_SUBMISSIONS_URL.format(cik=cik))
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            logger.error("Failed to fetch SEC submissions for %s: %s", ticker, exc)
            return []
        company_name = data.get("name", ticker.upper())
        recent = data.get("filings", {}).get("recent", {})

        filings: list[FilingInfo] = []
        forms = recent.get("form", [])
        for i, form in enumerate(forms):
            if form != filing_type:
                continue

            accession = recent["accessionNumber"][i]
            accession_clean = accession.replace("-", "")
            primary_doc = recent["primaryDocument"][i]
            cik_unpadded = str(int(cik))
            filing_url = f"{SEC_ARCHIVES_BASE}/{cik_unpadded}/{accession_clean}/{primary_doc}"
            index_url = f"{SEC_ARCHIVES_BASE}/{cik_unpadded}/{accession_clean}/"

            filings.append(FilingInfo(
                ticker=ticker.upper(),
                company_name=company_name,
                filing_type=form,
                filing_date=recent.get("filingDate", [""])[i],
                report_date=recent.get("reportDate", [""])[i],
                accession_number=accession,
                filing_url=filing_url,
                index_url=index_url,
                primary_document=primary_doc,
            ))
            if len(filings) >= count:
                break

        return filings
    finally:
        if own_client:
            client.close()


def fetch_filing_text(filing_url: str, client: httpx.Client, max_chars: int = 180_000) -> str:
    try:
        response = client.get(filing_url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("Failed to download SEC filing %s: %s", filing_url, exc)
        return ""
    html = response.text
    text = _html_to_text(html)
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n[... truncated for processing ...]"
    return text


def extract_key_sections(text: str) -> dict[str, str]:
    """Extract common 10-K / 10-Q sections from normalized filing text."""
    patterns = [
        ("Business Overview", r"(?:Item\s+1[.\s-]+Business)(.*?)(?:Item\s+1A[.\s-]+Risk\s+Factors|Item\s+2[.\s-]+Properties)"),
        ("Risk Factors", r"(?:Item\s+1A[.\s-]+Risk\s+Factors)(.*?)(?:Item\s+1B|Item\s+2[.\s-]+Properties|Item\s+3[.\s-]+Legal)"),
        ("Management Discussion", r"(?:Item\s+7[.\s-]+Management'?s?\s+Discussion.*?)(.*?)(?:Item\s+7A|Item\s+8[.\s-]+Financial\s+Statements)"),
        ("Financial Statements", r"(?:Item\s+8[.\s-]+Financial\s+Statements.*?)(.*?)(?:Item\s+9|Item\s+9A|Part\s+III)"),
        ("Quarterly MD&A", r"(?:Item\s+2[.\s-]+Management'?s?\s+Discussion.*?)(.*?)(?:Item\s+3|Item\s+4|Part\s+II)"),
        ("Controls And Procedures", r"(?:Item\s+4[.\s-]+Controls\s+and\s+Procedures)(.*?)(?:Part\s+II|Item\s+1[.\s-]+Legal)"),
    ]

    sections: dict[str, str] = {}
    for title, pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        section_text = _squash_whitespace(match.group(1))
        if len(section_text) > 20_000:
            section_text = section_text[:20_000] + "\n\n[... truncated ...]"
        if len(section_text) > 300:
            sections[title] = section_text
    return sections


def save_filing_markdown(
    filing: FilingInfo,
    text: str,
    sections: dict[str, str],
    output_dir: Path,
) -> Path:
    filename = f"{filing.ticker}_{filing.filing_type.replace('-', '')}_{filing.filing_date}.md"
    path = output_dir / filename

    lines = [
        f"# {filing.company_name} {filing.filing_type} Filing",
        "",
        "## Filing Metadata",
        f"- Company: {filing.company_name}",
        f"- Ticker: {filing.ticker}",
        f"- Filing type: {filing.filing_type}",
        f"- Filing date: {filing.filing_date}",
        f"- Report date: {filing.report_date}",
        f"- Accession number: {filing.accession_number}",
        f"- Source URL: {filing.filing_url}",
        f"- Index URL: {filing.index_url}",
        "- Source: SEC EDGAR",
        "",
    ]

    if sections:
        for section_title, section_text in sections.items():
            lines.extend([f"## {section_title}", "", section_text.strip(), ""])
    else:
        lines.extend(["## Filing Text", "", text[:60_000].strip(), ""])

    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Saved %s (%d chars)", path, path.stat().st_size)
    return path


def _html_to_text(html: str) -> str:
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<[^>]+>", " ", html)
    html = unescape(html)
    return _squash_whitespace(html)


def _squash_whitespace(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


if __name__ == "__main__":
    main()
