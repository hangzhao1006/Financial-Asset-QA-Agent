# Implementation Sync

This document summarizes the current implementation state of the Financial Asset QA System and the main changes made after the initial project plan. It is intended as the handoff/reference document for future development.

## Current Positioning

FinQ is now a compact financial asset QA system with four core capabilities:

1. Real-time or fallback market quote/trend lookup.
2. Financial concept QA using a local RAG-style knowledge base.
3. Company report QA using curated report documents when source material exists.
4. Agent observability with Decision / Action / Observation traces.

The current design favors a stable demo-quality system over broad crawling or unlimited open-domain financial answering. When the system lacks evidence, it refuses unsupported summaries instead of fabricating numbers.

## Major Changes From Initial Plan

### Agent Routing And Fast Paths

The original agent pipeline remains:

```text
context_loader -> intent_classifier -> entity_resolver -> planner -> tool_executor
-> fallback_handler -> evidence_validator -> answer_composer
-> self_checker -> safety_checker -> context_writer
```

The implementation now also includes deterministic fast paths before the full LangGraph-style pipeline:

- `fast_quote`: handles simple current price questions without LLM/RAG latency.
- `fast_trend`: handles recent movement/trend questions such as "past 7 days" or "最近 7 天涨跌".
- `fast_fundamentals`: handles company-specific P/E ratio questions and supports follow-up memory.
- `fast_knowledge`: handles common financial concepts such as P/E ratio, revenue vs net income, free cash flow, and gross margin.
- `private_company_check`: detects private companies such as ByteDance/OpenAI and refuses to invent public stock prices.
- `missing_source_check`: detects report-specific questions where no local company report exists and refuses unsupported summaries.

This makes common demo questions faster and more reliable while preserving the full pipeline for broader questions.

### ReAct-Style Agent Trace

`agent_steps` now keeps the original fields:

```text
node, detail, status
```

and adds optional fields:

```text
decision, action, action_input, observation
```

The frontend now displays these fields in the step expander, closer to the notebook-style Action / Observation pattern.

### Market Data Fallbacks

The market data layer now uses a layered fallback strategy:

- Try AKShare / Yahoo Finance style providers where available.
- Fall back to local demo quote/history/fundamental values for common demo assets.
- Mark fallback/demo data clearly through provider and warnings.

This keeps charts and quote cards usable during demos even when external providers fail.

### Session Memory

Session IDs are persisted in frontend localStorage, so refreshes keep conversation context. Fast paths now also save turns to session memory, which fixes follow-up questions such as:

```text
阿里巴巴当前股价是多少？
他的市盈率呢？
```

`SessionStore` now also exposes compatibility APIs used by tests:

```text
add_turn(session_id, turn)
get_memory(session_id)
max_turns
```

### Knowledge QA And Hallucination Guardrails

The original knowledge QA path could call LLM composition even when RAG returned no chunks. This caused hallucinated answers for source-specific questions, for example invented report numbers.

Current behavior:

- General concepts may use local concept fallback when RAG/LLM is unavailable.
- Source-specific questions, such as quarterly report summaries, require retrieved evidence.
- If no matching source material exists, the system returns an evidence-limited response instead of inventing data.

Example:

```text
华为最近季度财报摘要是什么
```

If the knowledge base has no Huawei report material, the system answers that no citable material was found and asks the user to ingest a report first.

### RAG Knowledge Base And Chunking

The Markdown chunker now splits oversized paragraphs by token windows, instead of returning a single huge chunk. This fixed the large-section chunking test and improves retrieval granularity.

The ingestion script now recursively reads:

```text
knowledge_base/**/*.md
```

so generated report documents under `knowledge_base/company_reports/` are included automatically.

Source URLs embedded in Markdown are extracted into metadata for source display.

### Evaluation

Two evaluation layers are in use:

- `backend/evals/run_system_eval.py`
- `backend/evals/run_benchmark.py`

The benchmark now includes a hard failure gate for error-style answers such as connection errors, preventing false positives.

Current verified results after the latest changes:

```text
pytest backend/tests/ -v: 33 passed
system eval: 11/11 passed
benchmark: 10/10 passed
frontend build: passed
```

## Company Report Data Pipeline

The project now has a small, curated financial report ingestion pipeline:

```text
data_sources/reports_manifest.yaml
backend/scripts/fetch_reports.py
knowledge_base/company_reports/
backend/scripts/ingest_knowledge_base.py
```

### Manifest-Driven PDF/HTML Pipeline

The current implemented approach is manifest-driven:

1. Maintain a small list of official report URLs in `data_sources/reports_manifest.yaml`.
2. Run `backend.scripts.fetch_reports`.
3. The script downloads PDF/HTML files into `data_sources/raw_reports/`.
4. It extracts text using `pypdf` for text-based PDFs or a simple HTML parser for HTML pages.
5. It generates normalized Markdown files in `knowledge_base/company_reports/`.
6. Run `backend.scripts.ingest_knowledge_base` to ingest the generated Markdown into Chroma.

Commands:

```bash
backend/.venv/bin/python -m backend.scripts.fetch_reports
backend/.venv/bin/python -m backend.scripts.ingest_knowledge_base
```

or:

```bash
backend/.venv/bin/python -m backend.scripts.fetch_reports --ingest
```

This approach is ideal for the current demo because it is stable, transparent, and source-controlled.

## SEC EDGAR Recommendation

Claude suggested using SEC EDGAR API:

```text
EDGAR API -> filing list -> filing text -> LLM summary -> RAG knowledge base
```

This is a good long-term direction, especially for US-listed companies.

### Benefits

- Free and official.
- Covers US-listed companies.
- Supports structured filing lookup for 10-K and 10-Q.
- Avoids manually searching each company investor relations site.
- Better suited to repeatable ingestion than random web crawling.

### Limitations

- It mainly covers SEC filers, not all global companies.
- It does not cover Huawei, because Huawei is not a US-listed SEC filer.
- SEC filings are often long HTML/XBRL documents and still require extraction, section filtering, and cleanup.
- Full filing text can be noisy; dumping entire filings into RAG may hurt retrieval quality.
- LLM-generated summaries should not replace raw source chunks; summaries should be stored alongside source excerpts.

### Recommended Decision

Use a two-track design:

1. **Keep the current manifest PDF/HTML pipeline** for demo coverage and non-US companies such as Huawei.
2. **Add EDGAR as an optional second provider** for US-listed companies such as Apple, Tesla, Microsoft, Nvidia, Amazon, and Alibaba ADS-related filings.

This gives the best balance:

- Stable demo now.
- Clear engineering extension path.
- Official data sources.
- No need for large-scale scraping.

## SEC EDGAR Provider

SEC EDGAR support has been integrated into the existing report fetcher:

```text
backend/scripts/fetch_reports.py
```

There is also a dedicated ad-hoc CLI matching the common EDGAR workflow:

```text
backend/scripts/fetch_filings.py
```

Current flow:

```text
ticker -> CIK lookup
-> SEC submissions API
-> latest 10-K / 10-Q accession number
-> filing document URL
-> extract filing text
-> generate normalized Markdown
-> save to knowledge_base/company_reports/
-> ingest into Chroma
```

Manifest examples:

```yaml
reports:
  - company: Apple
    ticker: AAPL
    provider: sec_edgar
    filing_type: 10-K
    period: latest
    enabled: true

  - company: Tesla
    ticker: TSLA
    provider: sec_edgar
    filing_type: 10-Q
    period: latest
    enabled: true

  - company: Huawei
    provider: official_pdf
    url: https://...
    period: "2024 Annual"
    enabled: true
```

Important implementation detail: SEC requires a descriptive User-Agent. Any EDGAR script should set something like:

```text
User-Agent: FinQ demo contact@example.com
```

The current script reads this from `SEC_USER_AGENT` or `--sec-user-agent`.

Ad-hoc examples:

```bash
backend/.venv/bin/python -m backend.scripts.fetch_filings --ticker TSLA --type 10-K --count 2
backend/.venv/bin/python -m backend.scripts.fetch_filings --ticker TSLA --type 10-Q --count 4
backend/.venv/bin/python -m backend.scripts.fetch_filings --ticker AAPL --type 10-K --list-only
backend/.venv/bin/python -m backend.scripts.fetch_filings --all --type 10-K
```

`fetch_filings.py` saves Markdown to `knowledge_base/filings/`, which is already covered by recursive ingestion.

## Practical Recommendation

For the project as it stands:

1. Use the implemented manifest PDF/HTML pipeline immediately.
2. Curate 3-5 company report examples:
   - Huawei annual report from official PDF.
   - Apple 10-K or annual financial statements.
   - Tesla quarterly update.
   - Alibaba quarterly/annual result.
   - Tencent annual/quarterly report.
3. Use EDGAR support for US-listed companies while retaining `official_pdf` for non-SEC companies.

This avoids turning the project into a large crawler while still proving the system can ingest real company reports and answer report-specific RAG questions with evidence.
