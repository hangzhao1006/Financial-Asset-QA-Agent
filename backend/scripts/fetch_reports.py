"""Fetch curated financial reports and convert them into Markdown for RAG.

This is intentionally manifest-driven instead of a broad crawler. Keep a small
list of official report URLs in data_sources/reports_manifest.yaml, run this
script, then ingest the generated Markdown into Chroma.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = _PROJECT_ROOT / "data_sources" / "reports_manifest.yaml"
DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "knowledge_base" / "company_reports"
DEFAULT_RAW_DIR = _PROJECT_ROOT / "data_sources" / "raw_reports"
DEFAULT_SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "FinQ demo contact@example.com")
SEC_TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik_padded}.json"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

KEYWORD_PATTERNS = [
    "revenue", "net income", "net profit", "operating income", "gross margin",
    "cash flow", "free cash flow", "research and development", "risk factors",
    "business highlights", "financial highlights", "outlook",
    "收入", "净利润", "经营利润", "毛利率", "现金流", "自由现金流",
    "研发", "业务亮点", "风险", "展望",
]


@dataclass
class ReportItem:
    company: str
    ticker: str
    period: str
    report_type: str
    provider: str = "official_pdf"
    filing_type: str = ""
    url: str = ""
    local_path: str = ""
    enabled: bool = True
    aliases: list[str] | None = None
    headers: dict[str, str] | None = None
    ocr: bool = False
    ocr_lang: str = "chi_sim+chi_tra+eng"
    notes: str = ""


class _TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag in {"p", "br", "div", "section", "article", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag in {"p", "div", "section", "article", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            stripped = data.strip()
            if stripped:
                self.parts.append(stripped + " ")

    def text(self) -> str:
        return "\n".join(self.parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch financial reports into Markdown knowledge base files.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Path to reports manifest YAML.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Markdown output directory.")
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR), help="Downloaded raw file directory.")
    parser.add_argument("--max-pages", type=int, default=80, help="Maximum PDF pages to extract.")
    parser.add_argument("--max-chars", type=int, default=120_000, help="Maximum cleaned text chars to keep.")
    parser.add_argument("--force", action="store_true", help="Overwrite already-downloaded raw files.")
    parser.add_argument("--include-disabled", action="store_true", help="Also process manifest entries with enabled: false.")
    parser.add_argument("--ingest", action="store_true", help="Run backend.scripts.ingest_knowledge_base after writing Markdown.")
    parser.add_argument("--sec-user-agent", default=DEFAULT_SEC_USER_AGENT, help="SEC EDGAR User-Agent header.")
    parser.add_argument("--ocr", action="store_true", help="OCR PDF pages instead of extracting embedded text.")
    parser.add_argument("--ocr-lang", default="chi_sim+chi_tra+eng", help="Tesseract languages, e.g. chi_sim+chi_tra+eng.")
    args = parser.parse_args()

    written = run(
        manifest_path=Path(args.manifest),
        output_dir=Path(args.output_dir),
        raw_dir=Path(args.raw_dir),
        max_pages=args.max_pages,
        max_chars=args.max_chars,
        force=args.force,
        include_disabled=args.include_disabled,
        sec_user_agent=args.sec_user_agent,
        force_ocr=args.ocr,
        ocr_lang=args.ocr_lang,
    )

    print(f"Generated {len(written)} Markdown report file(s).")
    for path in written:
        print(f"  - {path}")

    if args.ingest:
        print("Running RAG ingestion...")
        subprocess.run(
            [sys.executable, "-m", "backend.scripts.ingest_knowledge_base"],
            cwd=str(_PROJECT_ROOT),
            check=True,
        )


def run(
    manifest_path: Path,
    output_dir: Path,
    raw_dir: Path,
    max_pages: int,
    max_chars: int,
    force: bool,
    include_disabled: bool,
    sec_user_agent: str,
    force_ocr: bool,
    ocr_lang: str,
) -> list[Path]:
    reports = _load_manifest(manifest_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    default_headers = _browser_headers(sec_user_agent)
    with httpx.Client(follow_redirects=True, timeout=45.0, headers=default_headers) as client:
        for report in reports:
            if not report.enabled and not include_disabled:
                print(f"Skipping disabled report: {report.company} {report.period}")
                continue

            try:
                raw_path = _materialize_report(report, raw_dir, client, force=force)
                use_ocr = force_ocr or report.ocr
                text = _extract_text(
                    raw_path,
                    max_pages=max_pages,
                    ocr=use_ocr,
                    ocr_lang=report.ocr_lang or ocr_lang,
                )
                text = _clean_text(text)[:max_chars]
                if len(text) < 500:
                    print(f"Warning: extracted text is short for {report.company}: {len(text)} chars")

                markdown = _render_markdown(report, raw_path, text)
                out_path = output_dir / f"{_slug(report.company)}_{_slug(report.period)}_{_slug(report.report_type)}.md"
                out_path.write_text(markdown, encoding="utf-8")
                written.append(out_path)
            except Exception as exc:
                print(f"Failed {report.company} {report.period}: {exc}", file=sys.stderr)

    return written


def _load_manifest(path: Path) -> list[ReportItem]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = data.get("reports", [])
    reports = []
    for item in items:
        reports.append(ReportItem(
            company=str(item.get("company", "")).strip(),
            ticker=str(item.get("ticker", "")).strip(),
            period=str(item.get("period", "")).strip(),
            report_type=str(item.get("report_type", item.get("type", "report"))).strip(),
            provider=str(item.get("provider", "official_pdf")).strip(),
            filing_type=str(item.get("filing_type", "")).strip(),
            url=str(item.get("url", "")).strip(),
            local_path=str(item.get("local_path", "")).strip(),
            enabled=bool(item.get("enabled", True)),
            aliases=list(item.get("aliases", []) or []),
            headers={str(k): str(v) for k, v in (item.get("headers", {}) or {}).items()},
            ocr=bool(item.get("ocr", False)),
            ocr_lang=str(item.get("ocr_lang", "chi_sim+chi_tra+eng")).strip(),
            notes=str(item.get("notes", "")).strip(),
        ))
    return [r for r in reports if r.company and (r.url or r.local_path or r.provider == "sec_edgar")]


def _materialize_report(report: ReportItem, raw_dir: Path, client: httpx.Client, force: bool) -> Path:
    if report.provider == "sec_edgar":
        return _materialize_sec_report(report, raw_dir, client, force=force)

    if report.local_path:
        path = Path(report.local_path)
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        if not path.exists():
            raise FileNotFoundError(path)
        return path

    suffix = _suffix_from_url(report.url)
    raw_name = f"{_slug(report.company)}_{_slug(report.period)}_{_hash(report.url)}{suffix}"
    raw_path = raw_dir / raw_name
    if raw_path.exists() and not force:
        return raw_path

    response = client.get(report.url, headers=_report_headers(report, client.headers))
    response.raise_for_status()
    raw_path.write_bytes(response.content)
    return raw_path


def _browser_headers(user_agent: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent if user_agent and "example.com" not in user_agent else (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }


def _report_headers(report: ReportItem, base_headers) -> dict[str, str]:
    headers = dict(base_headers)
    if report.headers:
        headers.update(report.headers)
    return headers


def _materialize_sec_report(report: ReportItem, raw_dir: Path, client: httpx.Client, force: bool) -> Path:
    if not report.ticker:
        raise ValueError("SEC EDGAR report requires ticker")

    cik = _lookup_sec_cik(report.ticker, client)
    filing = _latest_sec_filing(cik, report.filing_type or report.report_type or "10-K", client)

    accession = filing["accessionNumber"]
    accession_nodash = accession.replace("-", "")
    primary_doc = filing["primaryDocument"]
    cik_int = str(int(cik))
    filing_url = f"{SEC_ARCHIVES_BASE}/{cik_int}/{accession_nodash}/{primary_doc}"

    report.url = filing_url
    report.period = report.period if report.period and report.period != "latest" else filing.get("reportDate") or filing.get("filingDate") or "latest"
    report.report_type = filing.get("form", report.report_type)

    suffix = _suffix_from_url(filing_url)
    raw_name = f"{_slug(report.company)}_{_slug(report.report_type)}_{_slug(report.period)}_{accession_nodash}{suffix}"
    raw_path = raw_dir / raw_name
    if raw_path.exists() and not force:
        return raw_path

    response = client.get(filing_url)
    response.raise_for_status()
    raw_path.write_bytes(response.content)
    return raw_path


def _lookup_sec_cik(ticker: str, client: httpx.Client) -> str:
    response = client.get(SEC_TICKER_CIK_URL)
    response.raise_for_status()
    data = response.json()
    ticker_upper = ticker.upper()
    for entry in data.values():
        if str(entry.get("ticker", "")).upper() == ticker_upper:
            return str(entry["cik_str"]).zfill(10)
    raise ValueError(f"No SEC CIK found for ticker {ticker}")


def _latest_sec_filing(cik: str, filing_type: str, client: httpx.Client) -> dict:
    form = _normalize_sec_form(filing_type)
    response = client.get(SEC_SUBMISSIONS_URL.format(cik_padded=cik))
    response.raise_for_status()
    recent = response.json().get("filings", {}).get("recent", {})
    forms = recent.get("form", [])

    for i, candidate in enumerate(forms):
        if candidate == form:
            return {
                "form": candidate,
                "accessionNumber": recent["accessionNumber"][i],
                "primaryDocument": recent["primaryDocument"][i],
                "filingDate": recent.get("filingDate", [""])[i],
                "reportDate": recent.get("reportDate", [""])[i],
            }

    raise ValueError(f"No recent {form} filing found for CIK {cik}")


def _normalize_sec_form(value: str) -> str:
    v = value.upper().replace("_", "-")
    if v in {"ANNUAL_REPORT", "ANNUAL"}:
        return "10-K"
    if v in {"QUARTERLY_REPORT", "QUARTERLY"}:
        return "10-Q"
    if v not in {"10-K", "10-Q"}:
        return "10-K"
    return v


def _extract_text(path: Path, max_pages: int, ocr: bool = False, ocr_lang: str = "chi_sim+chi_tra+eng") -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        if ocr:
            return _ocr_pdf_text(path, max_pages=max_pages, lang=ocr_lang)
        return _extract_pdf_text(path, max_pages=max_pages)
    if suffix in {".html", ".htm"}:
        return _extract_html_text(path.read_text(encoding="utf-8", errors="ignore"))
    return path.read_text(encoding="utf-8", errors="ignore")


def _extract_pdf_text(path: Path, max_pages: int) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required for PDF extraction. Install backend requirements first.") from exc

    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _ocr_pdf_text(path: Path, max_pages: int, lang: str) -> str:
    """Render PDF pages and OCR them with Tesseract.

    Requires the tesseract binary plus language packs installed on the system.
    On macOS: brew install tesseract tesseract-lang
    """
    try:
        import fitz
        import pytesseract
    except ImportError as exc:
        raise RuntimeError(
            "OCR requires pymupdf and pytesseract. Install backend requirements first."
        ) from exc
    if shutil.which("tesseract") is None:
        raise RuntimeError(
            "OCR requires the tesseract binary. On macOS, run: brew install tesseract tesseract-lang"
        )

    doc = fitz.open(path)
    texts: list[str] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, page in enumerate(doc[:max_pages]):
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image_path = Path(tmpdir) / f"page_{i + 1}.png"
            pix.save(image_path)
            page_text = pytesseract.image_to_string(str(image_path), lang=lang)
            texts.append(f"\n\n## OCR Page {i + 1}\n\n{page_text.strip()}")
    return "\n".join(texts)


def _extract_html_text(html: str) -> str:
    parser = _TextHTMLParser()
    parser.feed(html)
    return parser.text()


def _render_markdown(report: ReportItem, raw_path: Path, text: str) -> str:
    excerpts = _relevant_excerpts(text)
    aliases = ", ".join(report.aliases or [])
    source = report.url or str(raw_path)
    return f"""# {report.company} {report.period} {report.report_type}

## Report Metadata
- Company: {report.company}
- Ticker: {report.ticker}
- Aliases: {aliases}
- Period: {report.period}
- Report type: {report.report_type}
- Provider: {report.provider}
- Source URL: {source}
- Raw file: {raw_path.name}
- Notes: {report.notes}

## Relevant Extracts
{excerpts or "No keyword-focused excerpts were extracted. See full extracted text below."}

## Full Extracted Text
{text}
"""


def _relevant_excerpts(text: str, window: int = 2, max_blocks: int = 24) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    matches: list[tuple[int, str]] = []
    lowered_keywords = [k.lower() for k in KEYWORD_PATTERNS]
    for i, line in enumerate(lines):
        lower = line.lower()
        if any(keyword in lower for keyword in lowered_keywords):
            start = max(0, i - window)
            end = min(len(lines), i + window + 1)
            block = "\n".join(lines[start:end])
            matches.append((i, block))
        if len(matches) >= max_blocks:
            break

    rendered = []
    seen = set()
    for _, block in matches:
        key = block[:200]
        if key in seen:
            continue
        seen.add(key)
        rendered.append(f"> {block.replace(chr(10), chr(10) + '> ')}")
    return "\n\n".join(rendered)


def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _suffix_from_url(url: str) -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix in {".pdf", ".html", ".htm", ".txt", ".md"}:
        return suffix
    return ".html"


def _slug(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", value)
    return value.strip("_") or "report"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


if __name__ == "__main__":
    main()
