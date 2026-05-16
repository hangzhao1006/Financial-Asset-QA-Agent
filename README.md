# FinQ — 金融资产智能问答系统

FinQ is a full-stack financial asset QA system. It combines market data tools, report/knowledge RAG, a traceable Agent pipeline, streaming UI, and robust fallbacks for demo stability.

> 本项目仅用于学习、演示和研究，不构成投资建议。

## What It Does

- 查询股票当前价格、近期走势和基础指标。
- 解释金融概念，如市盈率、收入与净利润、自由现金流、毛利率。
- 基于公司财报、SEC 10-K / 10-Q 和本地知识库做 RAG 问答。
- 展示 Agent 执行轨迹，包括 `Decision`、`Action`、`Action Input`、`Observation`。
- 支持 SSE 流式输出、来源卡片、行情卡片和首页 Quick Asset Lookup。
- 外部服务失败时自动降级，避免页面白屏或模型编造答案。

## Current Status

当前系统已经完成核心链路：

- `Next.js + TypeScript + Tailwind CSS` frontend
- `FastAPI` backend
- LangGraph-style Agent pipeline
- Yahoo / AKShare market data integration
- Local demo market data fallback
- ChromaDB RAG
- Financial report ingestion
- SEC EDGAR 10-K / 10-Q ingestion
- Session memory
- ReAct-style agent trace
- Benchmark and system eval scripts
- Docker Compose setup

最近一次完整 benchmark：

```text
num_queries: 16
pass_count: 16
partial_count: 0
fail_count: 0
success_rate_pass_only: 1.0
avg_latency_sec: 3.22
error_count: 0
```

注意：测试时 OpenAI、Yahoo、AKShare 等外部网络请求可能失败。系统能通过 benchmark，是因为 planner fallback、market demo fallback、lexical RAG fallback 和 evidence-preserving answer fallback 生效。

## Architecture

```text
Next.js Frontend
  ├─ Quick Asset Lookup
  ├─ Chat UI
  ├─ Agent Steps
  ├─ Quote Cards
  └─ Source Cards
        │
        │ POST /api/ask or /api/ask/stream
        ▼
FastAPI Backend
  ├─ Fast paths
  │   ├─ fast_quote
  │   ├─ fast_trend
  │   ├─ fast_fundamentals
  │   └─ fast_knowledge
  │
  └─ Agent Pipeline
      context_loader
        → intent_classifier
        → entity_resolver
        → planner
        → tool_executor
        → fallback_handler
        → evidence_validator
        → answer_composer
        → self_checker
        → safety_checker
        → context_writer

Services
  ├─ Market Data: Yahoo / AKShare / Demo fallback
  ├─ RAG: ChromaDB / lexical fallback
  ├─ Reports: official PDF/HTML + SEC EDGAR
  ├─ Memory: short-term session store
  ├─ Cache: in-memory TTL
  └─ LLM: OpenAI-compatible API
```

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14, React, TypeScript, Tailwind CSS |
| Backend | FastAPI, Python |
| Agent | LangGraph-style node pipeline |
| LLM | OpenAI-compatible API |
| Embedding | `text-embedding-3-small` by default |
| Vector DB | ChromaDB |
| Market Data | Yahoo Finance / AKShare / local demo fallback |
| Report Data | Official PDF/HTML + SEC EDGAR |
| Evaluation | custom system eval + benchmark |
| Deployment | Docker Compose |

## Project Structure

```text
.
├── backend/
│   ├── app/
│   │   ├── agent/
│   │   │   ├── graph.py
│   │   │   ├── state.py
│   │   │   └── nodes/
│   │   ├── memory/
│   │   ├── prompts/
│   │   ├── services/
│   │   ├── config.py
│   │   ├── main.py
│   │   └── schemas.py
│   ├── evals/
│   ├── scripts/
│   └── tests/
├── data_sources/
│   └── reports_manifest.yaml
├── docs/
├── frontend/
│   └── src/
├── knowledge_base/
│   ├── company_reports/
│   └── filings/
├── documents/
│   └── financial_qa_plan_36ef1423.plan.md
├── docker-compose.yml
├── docker-shell.sh
└── README.md
```

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

```bash
OPENAI_API_KEY=your-openai-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
FALLBACK_LLM_MODEL=gpt-3.5-turbo
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
CHROMA_PERSIST_DIR=backend/.chroma
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Do not commit `.env`.

### 2. Backend

Run from the project root:

```bash
python -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt

python -m backend.scripts.ingest_knowledge_base
uvicorn backend.app.main:app --reload --port 8000
```

Check:

```text
http://localhost:8000/api/health
http://localhost:8000/docs
```

### 3. Frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Then visit:

```text
http://localhost:3000
```

If Next.js chooses another port, use the port printed in the terminal.

## Docker

```bash
cp .env.example .env
# edit .env
./docker-shell.sh
```

Or:

```bash
docker compose up --build
```

## API Endpoints

- `GET /api/health`
- `POST /api/ask`
- `POST /api/ask/stream`
- `GET /api/assets/resolve?query=BABA`
- `GET /api/assets/{symbol}/quote`
- `GET /api/assets/{symbol}/history?range=7d`
- `GET /api/assets/{symbol}/intraday?interval=15m`

## Agent Trace

Agent steps expose a ReAct-style trace:

```json
{
  "node": "tool_executor",
  "detail": "search_knowledge(4 chunks)",
  "status": "ok",
  "decision": "Need report evidence before answering.",
  "action": "search_knowledge",
  "action_input": {"query": "Apple 10-K risk factors"},
  "observation": "retrieved 4 knowledge chunks"
}
```

The frontend displays this in the collapsible Agent Steps panel.

## RAG Knowledge Base

Current knowledge sources:

- Core financial concept Markdown files.
- Company report Markdown files under `knowledge_base/company_reports/`.
- SEC filing Markdown files under `knowledge_base/filings/`.

Ingest:

```bash
python -m backend.scripts.ingest_knowledge_base
```

The script scans:

```text
knowledge_base/**/*.md
```

and writes chunks into ChromaDB.

Recent ingestion result:

```text
36 Markdown files
2818 chunks
ChromaDB path: backend/.chroma
```

## Financial Report Ingestion

The project supports two report ingestion paths.

### Path 1: SEC EDGAR

For US-listed companies:

```bash
python -m backend.scripts.fetch_filings --ticker AAPL --type 10-K --count 1
python -m backend.scripts.fetch_filings --ticker TSLA --type 10-Q --count 2
python -m backend.scripts.fetch_filings --all --type 10-K
```

Optional:

```bash
export SEC_USER_AGENT="FinQ demo your_email@example.com"
```

Output:

```text
knowledge_base/filings/
```

### Path 2: Official PDF / HTML

For China / HK / private companies:

1. Edit `data_sources/reports_manifest.yaml`.
2. Add official PDF/HTML URL or `local_path`.
3. Set `enabled: true`.
4. Run:

```bash
python -m backend.scripts.fetch_reports
python -m backend.scripts.ingest_knowledge_base
```

Or:

```bash
python -m backend.scripts.fetch_reports --ingest
```

Output:

```text
knowledge_base/company_reports/
data_sources/raw_reports/
```

### OCR Note

`fetch_reports.py` supports optional OCR for PDFs:

```yaml
ocr: true
ocr_lang: "chi_tra+eng"
```

OCR requires:

```bash
brew install tesseract tesseract-lang
pip install -r backend/requirements.txt
```

OCR is slower. For demo stability, prefer text-based PDF, official HTML, or SEC HTML filings.

Detailed guide:

```text
docs/REPORT_INGESTION_GUIDE.md
```

## Evaluation

### System Eval

```bash
python -m backend.evals.run_system_eval
```

This checks:

- market quote
- market trend
- financial concepts
- session memory follow-up

### Benchmark

```bash
python -m backend.evals.run_benchmark
```

Current benchmark has 16 cases:

- Q1-Q2: market quote and trend
- Q3/Q6/Q7: financial concepts
- Q4: event / causal question
- Q5: adversarial price guessing
- Q8-Q9: Chinese market questions
- Q10: investment advice safety
- Q11-Q16: report RAG

Latest result:

```text
16 / 16 pass
success_rate_pass_only = 1.0
```

Reports are written to:

```text
backend/evals/reports/
```

These reports are ignored by git because they are generated outputs.

## Fallback Behavior

The system is designed to degrade gracefully:

- If LLM planner fails, use deterministic planner.
- If answer composition fails, use local/evidence-preserving fallback.
- If embedding fails, use lexical RAG fallback.
- If market providers fail, use local demo market data.
- If news search fails, avoid unsupported causal claims.
- If no RAG source exists, refuse to summarize unsupported report data.

This is why benchmark can pass even when network requests fail.

## Known Data Quality Notes

- BYD generated Markdown currently appears to contain PDF.js viewer text rather than report body. Replace with a direct PDF or official exchange PDF before relying on it.
- Meituan PDFs have garbled embedded text. OCR is supported but slow; not recommended as the main demo path.
- Some SEC 10-Q files are short because extraction focuses on selected sections.

## Git / Push Safety

Before committing or pushing, make sure these are not tracked:

- `.env`
- `backend/.venv/`
- `frontend/node_modules/`
- `frontend/.next/`
- `backend/.chroma/`
- `data_sources/manual_reports/`
- `data_sources/raw_reports/`
- `*.pdf`
- `*.docx`
- `__pycache__/`
- `*.pyc`

Check tracked file count:

```bash
git ls-tree -r --name-only HEAD | wc -l
```

A clean initial commit is about 100-150 tracked files. If Git is trying to push tens of thousands of objects, stop and check whether dependency folders or generated artifacts are tracked.

Check for forbidden tracked files:

```bash
git ls-tree -r --name-only HEAD | grep -E '(\.env$|\.venv/|node_modules/|\.next/|\.chroma/|manual_reports/|raw_reports/|\.pdf$|\.docx$)' || true
```

`.env.example` must contain placeholders only.

## Future Work

- Re-apply or verify the preferred white minimalist financial UI if the current branch does not include it.
- Replace bad BYD viewer-derived files with real report PDFs.
- Add structured financial facts extraction for exact revenue, net profit, margin and cash flow questions.
- Add stronger source-aware RAG evaluation.
- Add local embedding dependency for fully offline RAG query embedding.
- Improve Docker image size and startup speed.

## License

MIT
