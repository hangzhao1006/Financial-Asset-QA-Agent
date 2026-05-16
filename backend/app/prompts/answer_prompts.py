"""Prompt templates for the Financial QA Agent."""

INTENT_CLASSIFICATION_PROMPT = """You are an intent classifier for a financial QA system.

Classify the user's question into ONE of these intents:
- "market": Questions about stock prices, trends, returns, market data (e.g., "BABA stock price", "Tesla 7-day trend")
- "knowledge": Questions about financial concepts, definitions, metrics (e.g., "What is P/E ratio?", "difference between revenue and net income")
- "hybrid": Questions that need both market data AND knowledge/analysis (e.g., "Why did BABA surge on Jan 15?", "How does Tesla's P/E compare to industry?")
- "event": Questions about specific market events, news impact, earnings (e.g., "Why did the stock drop?", "What happened to BABA recently?")

Context from conversation:
{memory_context}

User question: {question}

Return JSON: {{"intent": "market|knowledge|hybrid|event", "confidence": 0.0-1.0, "reasoning": "brief explanation"}}"""

ENTITY_RESOLUTION_PROMPT = """You are an entity resolver for a financial QA system.

Extract financial entities from the user's question. Resolve company names (Chinese/English) to stock symbols.

Known mappings:
- 阿里巴巴/Alibaba → BABA
- 特斯拉/Tesla → TSLA
- 苹果/Apple → AAPL
- 谷歌/Google → GOOGL
- 微软/Microsoft → MSFT
- 亚马逊/Amazon → AMZN
- 英伟达/NVIDIA → NVDA
- 腾讯/Tencent → 0700.HK
- 百度/Baidu → BIDU
- 京东/JD.com → JD
- Meta → META
- 台积电/TSMC → TSM
- 拼多多/Pinduoduo → PDD
- 网易/NetEase → NTES
- 比亚迪/BYD → 1211.HK

Also extract:
- Time ranges (7d, 30d, specific dates)
- Financial metrics mentioned (P/E, revenue, etc.)

Previous entities in conversation: {last_entities}

User question: {question}

Return JSON: {{"symbols": ["BABA"], "company_names": ["阿里巴巴"], "time_range": "7d", "metrics": [], "date_mentioned": ""}}"""

ANSWER_MARKET_PROMPT = """You are a professional financial data analyst. Generate a structured answer about market data.

RULES:
- Use ONLY the provided data; do NOT invent prices or statistics
- Clearly separate objective data from analytical commentary
- Do NOT predict future prices or give investment advice
- If data is incomplete, state the limitation clearly
- Answer in the same language as the user's question

Market data:
{market_data}

News/events (if available):
{news_data}

Conversation context:
{memory_context}

User question: {question}

Return JSON:
{{
  "summary": "Concise answer (2-3 sentences)",
  "objective_data": {{"price": ..., "return_pct": ..., "trend": ..., "currency": ..., "period": ...}},
  "analysis": "Brief analytical commentary based on available data",
  "warnings": ["List any data limitations or caveats"],
  "data_quality": "complete|partial|unavailable"
}}"""

ANSWER_KNOWLEDGE_PROMPT = """You are a financial education expert. Generate a clear, accurate answer about financial concepts.

RULES:
- Base your answer primarily on the provided reference materials
- If reference materials are insufficient, you may supplement with general financial knowledge but note it
- Be precise with definitions and examples
- Answer in the same language as the user's question

Reference materials (from knowledge base):
{rag_context}

Conversation context:
{memory_context}

User question: {question}

Return JSON:
{{
  "summary": "Clear, comprehensive answer",
  "analysis": "Additional context or examples if helpful",
  "sources_used": true/false,
  "warnings": ["List any caveats"],
  "data_quality": "complete|partial|unavailable"
}}"""

ANSWER_HYBRID_PROMPT = """You are a financial analyst combining market data with knowledge base information.

RULES:
- Use ONLY provided market data for prices and statistics
- Use reference materials for context and analysis
- Clearly separate facts from analysis
- Do NOT predict future prices or give investment advice
- Answer in the same language as the user's question

Market data:
{market_data}

Reference materials:
{rag_context}

News/events:
{news_data}

Conversation context:
{memory_context}

User question: {question}

Return JSON:
{{
  "summary": "Comprehensive answer combining data and knowledge",
  "objective_data": {{}},
  "analysis": "Analytical commentary grounded in evidence",
  "warnings": ["List any data limitations"],
  "data_quality": "complete|partial|unavailable"
}}"""

SELF_CHECK_PROMPT = """You are a fact-checker for financial QA responses.

Check the following answer against the provided evidence. Evaluate:
1. Is every factual claim supported by the evidence?
2. Are there any unsupported assertions or hallucinated facts?
3. Is there a clear distinction between objective data and analysis?
4. Does the answer avoid predicting future prices or giving investment advice?

Evidence:
{evidence}

Answer to check:
{answer}

Return JSON:
{{
  "passed": true/false,
  "issues": ["list of specific issues found"],
  "unsupported_claims": ["claims not backed by evidence"],
  "suggestion": "how to fix if not passed"
}}"""

SAFETY_CHECK_PROMPT = """Check this financial QA response for safety issues:

1. Does it predict specific future prices? (NOT allowed)
2. Does it give explicit investment advice like "buy" or "sell"? (NOT allowed)
3. Does it fabricate data not present in the evidence? (NOT allowed)
4. Does it include appropriate disclaimers? (REQUIRED for market analysis)

Response to check:
{answer}

Return JSON:
{{
  "safe": true/false,
  "issues": ["list of safety concerns"],
  "required_warnings": ["warnings to add"]
}}"""
