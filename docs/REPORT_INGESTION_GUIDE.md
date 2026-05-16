# 财报抓取与 RAG 导入手动指南

这份文档用于手动测试“财报数据进入 RAG”的完整流程。

当前项目同时支持两种财报来源：

1. `sec_edgar`：自动抓取美股上市公司的 SEC 10-K / 10-Q。
2. `official_pdf` / `official_html`：从公司官网、IR 页面或交易所公告下载 PDF/HTML。

最终生成的 Markdown 会被写入 `knowledge_base/filings/` 或 `knowledge_base/company_reports/`，再通过 `ingest_knowledge_base.py` 导入 ChromaDB。

## 前置准备

在项目根目录执行：

```bash
cd /Users/apple/Documents/GitHub/Financial-Asset-QA-system
source backend/.venv/bin/activate
```

确认依赖已安装：

```bash
backend/.venv/bin/python -m pip install -r backend/requirements.txt
```

SEC EDGAR 要求设置清晰的 User-Agent。请换成你自己的邮箱：

```bash
export SEC_USER_AGENT="FinQ demo your_email@example.com"
```

如果不设置，脚本会使用默认值，但正式测试时建议显式设置。

## 财报收录范围规范

为了避免 RAG 中时间范围混乱，建议统一按下面标准收录：

```text
US listed companies: latest 1 x 10-K + latest 1-2 x 10-Q
A-share companies: latest 1 annual report + latest 1 interim/quarterly report
HK-listed companies: latest 1 annual report + latest 1 interim report
Private/public-report-only companies: latest 1 annual report
```

Demo 最小集可以先做：

```text
AAPL: 1 x 10-K + 1 x 10-Q
TSLA: 1 x 10-K + 1 x 10-Q
Huawei: 1 x annual report
Tencent: 1 x annual report
BYD: 1 x annual report
Kweichow Moutai: 1 x annual report
```

如果某家公司暂时只有年报，也可以先只放年报。用户问季度报告时，系统会在没有来源时拒答，不会编造数据。

## 路径一：用 SEC EDGAR 抓美股财报

适合：

- Apple (`AAPL`)
- Tesla (`TSLA`)
- Microsoft (`MSFT`)
- Nvidia (`NVDA`)
- Amazon (`AMZN`)
- Meta (`META`)
- Google / Alphabet (`GOOGL`)
- Alibaba ADS (`BABA`)

### 只查看 filing URL

先用 `--list-only` 确认能访问 SEC：

```bash
backend/.venv/bin/python -m backend.scripts.fetch_filings \
  --ticker AAPL \
  --type 10-K \
  --count 1 \
  --list-only
```

如果成功，会打印类似：

```text
[AAPL] 10-K 2024-11-01 - https://www.sec.gov/Archives/...
```

### 下载单家公司年报

```bash
backend/.venv/bin/python -m backend.scripts.fetch_filings \
  --ticker TSLA \
  --type 10-K \
  --count 2
```

输出会写到：

```text
knowledge_base/filings/
```

文件名类似：

```text
TSLA_10K_2025-01-29.md
```

### 下载单家公司季报

```bash
backend/.venv/bin/python -m backend.scripts.fetch_filings \
  --ticker TSLA \
  --type 10-Q \
  --count 4
```

### 抓默认 8 家公司

```bash
backend/.venv/bin/python -m backend.scripts.fetch_filings \
  --all \
  --type 10-K \
  --count 1
```

默认公司：

```text
TSLA, AAPL, BABA, GOOGL, MSFT, NVDA, AMZN, META
```

### 抓完后导入 RAG

```bash
backend/.venv/bin/python -m backend.scripts.ingest_knowledge_base
```

`ingest_knowledge_base.py` 会递归读取：

```text
knowledge_base/**/*.md
```

所以 `knowledge_base/filings/` 会自动被导入。

## 路径二：用 manifest 抓官方 PDF / HTML

适合：

- 华为年报 PDF
- 腾讯财报 PDF
- 阿里巴巴 IR 页面
- 公司官网直接发布的 PDF/HTML

编辑：

```text
data_sources/reports_manifest.yaml
```

示例：

```yaml
reports:
  - company: Huawei
    aliases: ["华为", "huawei"]
    ticker: PRIVATE
    provider: official_pdf
    period: "2024 Annual"
    report_type: annual_report
    url: "https://www-file.huawei.com/-/media/corporate/pdf/annual-report/annual_report_2024_en.pdf"
    enabled: true
    notes: "Official Huawei annual report PDF."
```

然后运行：

```bash
backend/.venv/bin/python -m backend.scripts.fetch_reports
```

输出位置：

```text
data_sources/raw_reports/
knowledge_base/company_reports/
```

再导入 RAG：

```bash
backend/.venv/bin/python -m backend.scripts.ingest_knowledge_base
```

也可以一步完成：

```bash
backend/.venv/bin/python -m backend.scripts.fetch_reports --ingest
```

## 验证 RAG 是否可回答

重启后端：

```bash
uvicorn backend.app.main:app --reload --port 8000
```

然后在前端问：

```text
特斯拉最近 10-K 里提到了哪些风险？
Apple 最近年报的业务概述是什么？
华为 2024 年报摘要是什么？
```

如果 RAG 命中，回答下面应该显示来源卡，来源通常来自 Markdown metadata 中的 `Source URL`。

## 常见问题

### 1. SEC 返回 403

可能原因：

- 当前网络或代理拦截了 `sec.gov`。
- User-Agent 不符合 SEC 要求。
- 请求太频繁。

处理方式：

```bash
export SEC_USER_AGENT="FinQ demo your_email@example.com"
```

然后重试：

```bash
backend/.venv/bin/python -m backend.scripts.fetch_filings --ticker AAPL --type 10-K --list-only
```

如果仍然 403，说明当前网络环境访问 SEC 受限。可以换网络，或先使用 `official_pdf` manifest 方案。

### 2. PDF 抽出来文字很少或乱码

说明 PDF 可能是扫描版、图片型 PDF，或中文字体编码不适合直接文本抽取。可以开启 OCR，把每页渲染成图片后再识别文字。

先安装系统 OCR 引擎：

```bash
brew install tesseract tesseract-lang
backend/.venv/bin/python -m pip install -r backend/requirements.txt
```

然后在 manifest 条目中开启：

```yaml
ocr: true
ocr_lang: "chi_tra+eng"
```

或临时对全部 PDF 强制 OCR：

```bash
backend/.venv/bin/python -m backend.scripts.fetch_reports --ocr --ocr-lang chi_tra+eng --max-pages 20
```

OCR 更慢，但适合 Meituan 这类直接抽取后乱码的 PDF。如果 OCR 质量仍不够，建议换公司官网 HTML / SEC HTML filing，或手动整理一份 Markdown 放入 `knowledge_base/company_reports/`。

### 3. 官方 PDF 返回 403

有些公司 IR 的 PDF CDN 会做防盗链，例如部分 `todayir.com` 链接可能要求浏览器 Referer 或 Cookie。处理顺序建议：

1. 优先找交易所版本：
   - 港股：HKEX 披露易
   - A 股：上交所 / 深交所 / 巨潮资讯
2. 在 manifest 中给该条目添加 `headers.Referer`：

```yaml
headers:
  Referer: "https://www.example.com/investor-relations"
```

3. 如果仍然 403，就用浏览器手动下载 PDF 到本地，然后改用 `local_path`：

```yaml
- company: Meituan
  aliases: ["美团", "meituan", "03690"]
  ticker: "03690.HK"
  provider: official_pdf
  period: "2025 Annual"
  report_type: annual_report
  local_path: "data_sources/manual_reports/meituan_2025_annual.pdf"
  url: ""
  enabled: true
```

`fetch_reports.py` 支持 `local_path`，会直接解析本地 PDF，不再访问远程 URL。

### 4. 抓到了 Markdown，但问答仍说没有来源

检查是否跑了 ingest：

```bash
backend/.venv/bin/python -m backend.scripts.ingest_knowledge_base
```

然后重启后端。

也要确认 `.env` 中 embedding 可用：

- OpenAI 可用：配置 `OPENAI_API_KEY`。
- 离线 embedding：需要安装 `sentence-transformers` 并设置对应 provider。

### 5. 不想抓太多怎么办

建议只抓：

```text
AAPL 10-K count=1
TSLA 10-K count=1
MSFT 10-K count=1
Huawei official annual report count=1
```

这已经足够展示：

- SEC 自动财报抓取
- 官方 PDF 抽取
- RAG 对公司财报材料的问答
- 无来源时拒答

## 推荐手动测试顺序

1. 测 SEC 是否通：

```bash
backend/.venv/bin/python -m backend.scripts.fetch_filings --ticker AAPL --type 10-K --count 1 --list-only
```

2. 抓一份 Tesla 年报：

```bash
backend/.venv/bin/python -m backend.scripts.fetch_filings --ticker TSLA --type 10-K --count 1
```

3. 导入 RAG：

```bash
backend/.venv/bin/python -m backend.scripts.ingest_knowledge_base
```

4. 重启后端并提问：

```text
特斯拉最近年报的风险因素有哪些？
特斯拉最近 10-K 的业务概述是什么？
```

5. 如果 SEC 不通，改走 manifest 的官方 PDF：

```bash
backend/.venv/bin/python -m backend.scripts.fetch_reports --include-disabled
backend/.venv/bin/python -m backend.scripts.ingest_knowledge_base
```

注意：`--include-disabled` 会处理 manifest 中所有 disabled 条目，建议只在你确认 URL 可访问时使用；更稳的做法是只把需要的条目改为 `enabled: true`。
