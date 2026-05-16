# FinQ — 金融资产智能问答系统

> AI-powered Financial Asset QA System with real-time market data and RAG knowledge retrieval

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Next.js Frontend                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ Chat UI  │  │ Quote    │  │ Agent    │  │ Source    │  │
│  │          │  │ Card     │  │ Steps    │  │ Cards     │  │
│  └──────────┘  └──────────┘  └──────────┘  └───────────┘  │
│                    SSE Streaming                            │
└────────────────────────┬────────────────────────────────────┘
                         │ POST /api/ask/stream
┌────────────────────────▼────────────────────────────────────┐
│                   FastAPI Backend                            │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              LangGraph Agent Pipeline                  │ │
│  │                                                        │ │
│  │  context_loader → intent_classifier → entity_resolver  │ │
│  │       → planner → tool_executor → fallback_handler     │ │
│  │       → evidence_validator → answer_composer           │ │
│  │       → self_checker → safety_checker → context_writer │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Market Data  │  │  RAG Engine  │  │  News Search     │  │
│  │ (yfinance)   │  │  (ChromaDB)  │  │  (Tavily/Web)    │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Session      │  │  TTL Cache   │  │  LLM Client      │  │
│  │ Memory       │  │              │  │  (OpenAI API)     │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## 功能概览

**资产行情问答**（调用外部 API，非模型生成）
- 实时股价查询（中/英文资产名称均支持）
- 7日/30日涨跌幅计算与趋势分类
- 结构化数据与分析性描述分离
- 新闻检索辅助影响因素分析

**金融知识问答**（RAG 检索增强生成）
- 小型金融知识库（核心指标、财务报表、市场概念）
- 结构感知 Markdown 分块 + 向量化
- Query Rewrite → 向量检索 → Rerank → 证据校验
- Self-Check 降低幻觉

## 技术选型说明

| 层 | 技术 | 理由 |
|---|---|---|
| 前端 | Next.js 14 + TypeScript + Tailwind CSS | SSR 支持、路由代理、快速开发 |
| 后端 | FastAPI + Python | 异步性能、丰富的数据科学生态 |
| Agent | LangGraph 状态机 | 显式节点控制、可观测性强 |
| LLM | OpenAI-compatible API | 供应商无关，通过 base_url 切换 |
| 向量库 | ChromaDB | 轻量、本地持久化、适合小知识库 |
| Embedding | text-embedding-3-small | 多语言支持、成本低 |
| 行情 | Yahoo Finance (yfinance) | 免费、覆盖全球主要市场 |
| 搜索 | Tavily / SerpAPI | 结构化搜索结果，适合 Agent |
| 缓存 | In-memory TTL Cache | 分层 TTL，行情60s/RAG600s |

## Prompt 设计思路

系统采用分阶段 Prompt 设计：

1. **意图分类**：将用户问题分为 `market_quote`（报价）、`market_trend`（走势）、`knowledge`（知识）、`hybrid`（混合），确保路由正确。

2. **实体解析**：从自然语言中提取资产代码，支持中英文映射（如"阿里巴巴" → "BABA"）。

3. **回答组合**：根据意图类型使用不同 Prompt 模板：
   - 行情类：强制引用工具返回的客观数据，分析部分明确标注为推测。
   - 知识类：要求基于检索到的证据段落回答，未覆盖内容明确说明。

4. **自检机制**：生成回答后，Prompt 要求模型自评 faithfulness、completeness、clarity，低分则触发修正或警告。

5. **安全检查**：过滤投资建议、预测性语言、未经证实的强断言。

## 数据来源说明

- **股价/行情数据**：Yahoo Finance API (yfinance)，实时获取
- **金融知识**：本地 Markdown 知识库 → ChromaDB 向量检索
- **财报材料**：`data_sources/reports_manifest.yaml` 维护官方 PDF/HTML URL，`fetch_reports.py` 抽取文本并生成 Markdown
- **新闻/事件**：Tavily API / SerpAPI Web 搜索
- **LLM**：OpenAI-compatible API（可切换至其他模型）

## 快速开始

### 环境要求
- Python 3.11+
- Node.js 20+
- Docker (可选)

### 本地运行

```bash
# 1. 克隆项目
git clone <repo-url> && cd Financial-Asset-QA-system

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 OPENAI_API_KEY

# 3. 后端
cd backend
pip3 install -r requirements.txt
python -m scripts.ingest_knowledge_base  # 导入知识库
cd .. #到根目录
uvicorn backend.app.main:app --reload --port 8000

# 3.1 Test
http://localhost:8000/api/health

http://localhost:8000/api/assets/BABA/quote

# 4. 前端（另一个终端）
cd frontend
npm install
npm run dev

访问 http://localhost:3001
```

## 财报采集与 RAG 导入

项目支持一个小型、可控的财报采集 pipeline，适合 demo 使用。不要大规模爬取全网财报；推荐在 manifest 中维护少量官方来源。当前同时支持两类 provider：

- `official_pdf` / `official_html`：适合华为、腾讯、公司官网 PDF/HTML 财报。
- `sec_edgar`：适合 Apple、Tesla、Microsoft 等美股上市公司的 10-K / 10-Q。

1. 编辑 `data_sources/reports_manifest.yaml`，填入官方 PDF/HTML URL 或 SEC EDGAR 配置，并把需要采集的条目改为 `enabled: true`。

SEC EDGAR 需要设置合规的 User-Agent：

```bash
export SEC_USER_AGENT="FinQ demo your_email@example.com"
```

2. 生成 Markdown 财报知识库：

```bash
cd /Users/apple/Documents/GitHub/Financial-Asset-QA-system
backend/.venv/bin/python -m backend.scripts.fetch_reports
```

生成结果会写入：

```text
knowledge_base/company_reports/
data_sources/raw_reports/
```

3. 导入 Chroma RAG：

```bash
backend/.venv/bin/python -m backend.scripts.ingest_knowledge_base
```

也可以一步完成：

```bash
backend/.venv/bin/python -m backend.scripts.fetch_reports --ingest
```

如果只想临时抓取某个美股公司的 SEC 10-K / 10-Q，可以使用专用 EDGAR CLI：

```bash
# 特斯拉最近 2 份年报
backend/.venv/bin/python -m backend.scripts.fetch_filings --ticker TSLA --type 10-K --count 2

# 特斯拉最近 4 份季报
backend/.venv/bin/python -m backend.scripts.fetch_filings --ticker TSLA --type 10-Q --count 4

# 只列出 filing URL，不下载
backend/.venv/bin/python -m backend.scripts.fetch_filings --ticker AAPL --type 10-K --list-only

# 抓取默认 8 家美股公司
backend/.venv/bin/python -m backend.scripts.fetch_filings --all --type 10-K
```

`fetch_filings.py` 的输出目录是 `knowledge_base/filings/`，同样会被 `ingest_knowledge_base.py` 递归导入。

PDF 解析依赖 `pypdf`，适用于文字型 PDF。扫描版 PDF 暂不做 OCR；如果抽取文字很少，建议换官方 HTML/文本版或人工整理成 Markdown。

更详细的手动测试流程见：`docs/REPORT_INGESTION_GUIDE.md`。


### Docker 部署

```bash
cd ..
cp .env.example .env
# 编辑 .env

# 确保 .env 已配置好 OPENAI_API_KEY
./docker-shell.sh


# or 本地开发 （ 需手动启动前后端）
docker compose up --build
```

### 后端预览
```bash

http://localhost:8000/docs

http://localhost:8000/redoc

```

## 项目结构

```
├── backend/
│   ├── app/
│   │   ├── agent/
│   │   │   ├── nodes/        # 11个 Agent 节点
│   │   │   ├── graph.py      # Agent pipeline 组装
│   │   │   └── state.py      # AgentState 定义
│   │   ├── memory/           # 短期 Session 记忆
│   │   ├── prompts/          # Prompt 模板
│   │   ├── services/         # 业务服务层
│   │   │   ├── market_data.py    # 行情数据
│   │   │   ├── rag.py            # RAG 检索
│   │   │   ├── embedding.py      # Embedding
│   │   │   ├── reranker.py       # 重排序
│   │   │   ├── news_search.py    # 新闻搜索
│   │   │   ├── llm.py            # LLM 客户端
│   │   │   └── cache.py          # 分层缓存
│   │   ├── config.py         # 配置管理
│   │   ├── schemas.py        # 数据模型
│   │   └── main.py           # FastAPI 入口
│   ├── scripts/
│   │   └── ingest_knowledge_base.py
│   ├── evals/
│   │   └── rag_eval_dataset.json
│   └── config/
│       └── sources.yaml
├── frontend/
│   └── src/
│       ├── app/              # Next.js App Router
│       ├── components/       # React 组件
│       └── lib/              # API 客户端
├── knowledge_base/           # Markdown 金融知识库
├── docker-compose.yml
└── README.md
```

## 优化与扩展思考

**已实现的优化：**
- 分层 TTL 缓存减少重复调用
- Query Rewrite 提升检索质量
- Evidence Validator 校验数据一致性
- Self-Check 机制降低幻觉
- Safety Checker 过滤不当投资建议
- Session Memory 支持多轮追问

**可扩展方向：**
- 接入更多行情源（Alpha Vantage、Polygon.io）
- 扩展知识库（财报、研报、公告）
- 使用 Cross-Encoder Reranker 提升检索精度
- 添加用户认证和使用量限制
- 接入 WebSocket 实现真正的实时行情推送
- 使用 Redis 替代内存缓存支持水平扩展
- 多语言支持优化（目前已支持中英文混合查询）

## 评测

项目包含基于 RAGAS 框架的离线评测数据集 (`backend/evals/rag_eval_dataset.json`)，覆盖知识问答和行情问答两类场景，评测维度包括 faithfulness、answer relevancy、context precision 和 context recall。

```bash
cd /Users/apple/Documents/GitHub/Financial-Asset-QA-system
source backend/.venv/bin/activate

# 前提：知识库已导入
python -m backend.scripts.ingest_knowledge_base

# 运行评测
python -m backend.evals.run_ragas_eval
python -m evals.run_ragas_eval
```
```
评测数据集 (rag_eval_dataset.json, 10题)
      │
      ▼
  过滤出知识类问题（6题，排除行情类）
      │
      ▼
  对每题执行完整 RAG pipeline：
      │
      ├─ query rewrite（改写检索 query）
      ├─ embedding（向量化）
      ├─ ChromaDB 检索 top 8
      ├─ rerank 取 top 4
      └─ LLM 基于 evidence 生成回答
      │
      ▼
  收集 (question, answer, contexts, ground_truth)
      │
      ▼
  RAGAS 框架计算 4 个指标：
      │
      ├─ faithfulness     回答是否忠于检索到的证据
      ├─ answer_relevancy 回答与问题的相关度
      ├─ context_precision 检索到的上下文精确度
      └─ context_recall   检索是否覆盖了 ground truth
      │
      ▼
  输出报告到 backend/evals/reports/ragas_report_YYYYMMDD_HHMMSS.json

```
## License

MIT
