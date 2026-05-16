const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "";

export interface QuoteData {
  symbol: string;
  price: number | null;
  currency: string;
  timestamp: string | null;
  provider: string;
  error: string | null;
}

export interface HistoryPoint {
  date: string;
  close: number;
}

export interface HistoryData {
  symbol: string;
  range: string;
  data: HistoryPoint[];
  return_pct: number | null;
  trend: string | null;
  currency: string;
  provider: string;
  error: string | null;
}

export interface IntradayPoint {
  time: string;
  price: number;
  volume: number | null;
}

export interface IntradayData {
  symbol: string;
  interval: string;
  data: IntradayPoint[];
  current_price: number | null;
  change_pct: number | null;
  currency: string;
  provider: string;
  trading_status: string;
  warnings: string[];
  error: string | null;
}

export interface ResolveData {
  symbol: string;
  name: string;
  market: string;
  currency: string;
  found: boolean;
}

export interface AskResponse {
  answer_type: string;
  summary: string;
  objective_data: Record<string, unknown>;
  analysis: string;
  sources: Array<{
    type: string;
    title?: string;
    raw_title?: string;
    source_file?: string;
    url?: string;
    urls?: string[];
    section?: string;
    score?: number;
  }>;
  warnings: string[];
  agent_steps: Array<{
    node: string;
    detail: string;
    status: string;
    decision?: string;
    action?: string;
    action_input?: Record<string, unknown>;
    observation?: string;
  }>;
  cache_hit: boolean;
  fallback_used: boolean;
  data_quality: string;
  memory_used: boolean;
  self_check: Record<string, unknown>;
}

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

export async function fetchQuote(symbol: string): Promise<QuoteData> {
  const res = await fetch(`${API_BASE}/api/assets/${encodeURIComponent(symbol)}/quote`);
  if (!res.ok) throw new Error(`Quote fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchHistory(symbol: string, range = "7d"): Promise<HistoryData> {
  const res = await fetch(
    `${API_BASE}/api/assets/${encodeURIComponent(symbol)}/history?range=${range}`
  );
  if (!res.ok) throw new Error(`History fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchIntraday(symbol: string, interval = "15m"): Promise<IntradayData> {
  const res = await fetch(
    `${API_BASE}/api/assets/${encodeURIComponent(symbol)}/intraday?interval=${interval}`
  );
  if (!res.ok) throw new Error(`Intraday fetch failed: ${res.status}`);
  return res.json();
}

export async function resolveAsset(query: string): Promise<ResolveData> {
  const res = await fetch(`${API_BASE}/api/assets/resolve?query=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error(`Resolve failed: ${res.status}`);
  return res.json();
}

export async function askQuestion(question: string, sessionId?: string): Promise<AskResponse> {
  const res = await fetch(`${API_BASE}/api/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId }),
  });
  if (!res.ok) throw new Error(`Ask failed: ${res.status}`);
  return res.json();
}

export async function* askStream(
  question: string,
  sessionId?: string
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${API_BASE}/api/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId }),
  });

  if (!res.ok) throw new Error(`Stream failed: ${res.status}`);
  if (!res.body) throw new Error("No response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    let currentEvent = "";
    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        const dataStr = line.slice(6);
        try {
          const data = JSON.parse(dataStr);
          yield { event: currentEvent, data };
        } catch {
          // skip unparseable
        }
        currentEvent = "";
      }
    }
  }
}