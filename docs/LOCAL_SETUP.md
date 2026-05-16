# 本地运行指南 (Local Development Guide)

> 完整的从零开始到跑通示例问题的流程

---

## 0. 环境要求

| 工具 | 最低版本 | 检查命令 |
|------|---------|---------|
| Python | 3.11+ | `python --version` |
| Node.js | 20+ | `node --version` |
| npm | 9+ | `npm --version` |
| Git | 任意 | `git --version` |

你还需要一个 **OpenAI API Key**（或兼容 API 的 key）。

---

## 1. 克隆项目

```bash
git clone <your-repo-url> Financial-Asset-QA-system
cd Financial-Asset-QA-system
```

---

## 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，**至少填写以下一项**：

```bash
# 必填
OPENAI_API_KEY=your-openai-api-key

# 可选：如果用第三方兼容 API（如 DeepSeek / 智谱 / 本地 Ollama）
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

# 可选：新闻搜索（不填也能运行，只是无法搜新闻）
TAVILY_API_KEY=your-tavily-api-key
```

---

## 3. 启动后端

```bash
# 3.1 创建 Python 虚拟环境（推荐）
cd backend
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows
# .venv\Scripts\activate

# 3.2 安装依赖
pip install -r requirements.txt

# 3.3 回到项目根目录
cd ..

# 3.4 导入知识库到 ChromaDB（第一次运行必须执行）
python -m backend.scripts.ingest_knowledge_base

# 你应该看到类似输出：
# INFO:__main__:Processing 01_financial_metrics.md ...
# INFO:__main__:  -> 6 chunks
# INFO:__main__:Processing 02_financial_statements.md ...
# INFO:__main__:  -> 5 chunks
# INFO:__main__:Processing 03_market_fundamentals.md ...
# INFO:__main__:  -> 8 chunks
# INFO:__main__:Ingestion complete: 19 total chunks from 3 files

# 3.5 启动后端服务
uvicorn backend.app.main:app --reload --port 8000
```

验证后端是否正常：

```bash
# 另开一个终端
curl http://localhost:8000/api/health
# 应返回: {"status":"ok","version":"0.1.0"}

# 测试行情接口（不需要 API Key）
curl http://localhost:8000/api/assets/BABA/quote
# 应返回阿里巴巴的实时报价 JSON
```

---

## 4. 启动前端

**新开一个终端**：

```bash
cd frontend

# 4.1 安装依赖
npm install

# 4.2 启动开发服务器
npm run dev
```

打开浏览器访问：**http://localhost:3000**

---

## 5. 测试示例问题

在前端界面中点击示例问题按钮，或手动输入：

| 问题 | 预期行为 |
|------|---------|
| 阿里巴巴当前股价是多少？ | 调用 yfinance → 返回实时报价 + 数据卡片 |
| TSLA 最近 7 天涨跌如何？ | 调用 yfinance 历史 → 涨跌幅 + 趋势 + 迷你图 |
| 什么是市盈率？ | RAG 检索知识库 → 结构化知识回答 |
| 收入和净利润的区别是什么？ | RAG 检索 → 对比解释 |
| 苹果公司近期走势如何？ | "苹果公司" → AAPL → 调用行情 API |
| 那 30 天呢？ | Session memory 继承上次资产 → 查 30 天数据 |

---

## 6. 常见问题排查

### 后端启动报错 `ModuleNotFoundError`

确保你在**项目根目录**运行 uvicorn，而不是在 `backend/` 子目录：

```bash
# ✓ 正确（在项目根目录）
uvicorn backend.app.main:app --reload --port 8000

# ✗ 错误（在 backend/ 子目录）
cd backend && uvicorn app.main:app --reload
```

### `OPENAI_API_KEY` 报错

- 确认 `.env` 文件在项目根目录
- 确认 key 格式正确（`sk-` 开头）
- 如果用兼容 API，确认 `OPENAI_BASE_URL` 正确

### Ingest 知识库失败

- 如果 OpenAI embedding 失败，脚本会尝试使用本地 `BAAI/bge-m3` 模型（需要额外安装 `sentence-transformers`）
- 确认 `.env` 中 `OPENAI_API_KEY` 已填写

### 前端连不上后端

- 确认后端运行在 `http://localhost:8000`
- Next.js 默认通过 `next.config.js` 中的 rewrite 代理 `/api/*` 请求到后端
- 如果端口不同，修改 `frontend/next.config.js` 中的 `NEXT_PUBLIC_API_URL`

### yfinance 行情获取失败

- yfinance 不需要 API Key，但依赖 Yahoo Finance 服务
- 某些网络环境可能需要代理
- 检查 symbol 是否正确（如 `BABA`, `AAPL`, `TSLA`）

---

## 7. 项目目录速览

```
Financial-Asset-QA-system/
├── .env                          ← 你的 API Keys（不提交到 Git）
├── .env.example                  ← 环境变量模板
├── docker-shell.sh               ← Docker 快捷启动脚本
├── docker-compose.yml            ← Docker Compose 配置
│
├── backend/
│   ├── requirements.txt          ← Python 依赖
│   ├── app/
│   │   ├── main.py               ← FastAPI 入口
│   │   ├── config.py             ← 配置管理
│   │   ├── schemas.py            ← 数据模型
│   │   ├── agent/                ← LangGraph Agent
│   │   │   ├── state.py          ← Agent 状态定义
│   │   │   ├── graph.py          ← Pipeline 组装
│   │   │   └── nodes/            ← 11 个处理节点
│   │   ├── services/             ← 业务服务
│   │   │   ├── market_data.py    ← yfinance 行情
│   │   │   ├── rag.py            ← RAG 检索
│   │   │   ├── embedding.py      ← Embedding
│   │   │   ├── llm.py            ← LLM 调用
│   │   │   └── cache.py          ← TTL 缓存
│   │   ├── memory/               ← Session 记忆
│   │   └── prompts/              ← Prompt 模板
│   ├── scripts/
│   │   └── ingest_knowledge_base.py  ← 知识库导入
│   └── evals/                    ← RAGAS 评测
│
├── frontend/
│   ├── package.json
│   └── src/
│       ├── app/page.tsx          ← 主页面
│       ├── components/           ← UI 组件
│       └── lib/api.ts            ← API 客户端
│
└── knowledge_base/               ← Markdown 金融知识库
    ├── 01_financial_metrics.md
    ├── 02_financial_statements.md
    └── 03_market_fundamentals.md
```

---

## 8. Docker 一键启动（替代方案）

如果不想本地安装 Python 和 Node.js：

```bash
cp .env.example .env
# 编辑 .env 填入 OPENAI_API_KEY

# 方式 A：用脚本
./docker-shell.sh

# 方式 B：直接用 docker compose
docker compose up --build
```

然后访问 http://localhost:3000
