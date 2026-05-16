"use client";

interface Props {
  data: Record<string, unknown>;
}

function formatNumber(n: unknown): string {
  if (n == null) return "—";
  const num = Number(n);
  if (isNaN(num)) return String(n);
  if (Math.abs(num) >= 1e12) return `${(num / 1e12).toFixed(2)}T`;
  if (Math.abs(num) >= 1e9) return `${(num / 1e9).toFixed(2)}B`;
  if (Math.abs(num) >= 1e6) return `${(num / 1e6).toFixed(2)}M`;
  return num.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function formatPrice(n: unknown): string {
  if (n == null) return "—";
  return Number(n).toFixed(2);
}

export default function QuoteCard({ data }: Props) {
  const d = data as Record<string, unknown>;
  const price = d.price ?? d.current_price;
  const change = d.change_percent ?? d.change_pct;
  const changeNum = Number(change);
  const isPositive = changeNum > 0;
  const isNegative = changeNum < 0;
  const symbolStr = String(d.symbol || d.ticker || "—");
  const nameStr = d.name ? String(d.name) : "";
  const trendStr = d.trend ? String(d.trend) : "";

  // If data has history array, show mini trend
  const history = d.history as Array<{ date: string; close: number }> | undefined;

  return (
    <div className="panel max-w-[92%] px-5 py-4">
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded bg-surface-2 px-2 py-0.5 font-mono text-xs text-slate-600">
              {symbolStr}
            </span>
            {nameStr && (
              <span className="text-sm text-slate-500">{nameStr}</span>
            )}
          </div>
          {price != null && (
            <div className="mt-1 flex items-baseline gap-3">
              <span className="font-display text-2xl font-semibold text-slate-950">
                ${formatPrice(price)}
              </span>
              {change != null && (
                <span
                  className={`text-sm font-medium ${
                    isPositive
                      ? "text-brand-500"
                      : isNegative
                      ? "text-accent-red"
                      : "text-slate-500"
                  }`}
                >
                  {isPositive ? "+" : ""}
                  {formatPrice(change)}%
                </span>
              )}
            </div>
          )}
        </div>

        {trendStr && (
          <span
            className={`text-xs px-2 py-1 rounded-lg ${
              trendStr === "上涨"
                ? "bg-brand-500/10 text-brand-400"
                : trendStr === "下跌"
                ? "bg-accent-red/10 text-accent-red"
                : "bg-accent-gold/10 text-accent-gold"
            }`}
          >
            {trendStr}
          </span>
        )}
      </div>

      {/* Mini data grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-2 text-[11px]">
        {d.market_cap != null && (
          <div>
            <span className="text-slate-500">市值</span>
            <span className="ml-1 text-slate-700">{formatNumber(d.market_cap)}</span>
          </div>
        )}
        {d.volume != null && (
          <div>
            <span className="text-slate-500">成交量</span>
            <span className="ml-1 text-slate-700">{formatNumber(d.volume)}</span>
          </div>
        )}
        {d.pe_ratio != null && (
          <div>
            <span className="text-slate-500">PE</span>
            <span className="ml-1 text-slate-700">{formatPrice(d.pe_ratio)}</span>
          </div>
        )}
        {d.high_52w != null && (
          <div>
            <span className="text-slate-500">52W H/L</span>
            <span className="ml-1 text-slate-700">
              {formatPrice(d.high_52w)} / {formatPrice(d.low_52w)}
            </span>
          </div>
        )}
      </div>

      {/* Mini sparkline using SVG */}
      {history && history.length > 1 && (
        <div className="mt-3 pt-3 border-t border-surface-3">
          <MiniChart data={history} />
        </div>
      )}
    </div>
  );
}

function MiniChart({ data }: { data: Array<{ date: string; close: number }> }) {
  const closes = data.map((d) => d.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const w = 280;
  const h = 50;

  const points = closes
    .map((c, i) => {
      const x = (i / (closes.length - 1)) * w;
      const y = h - ((c - min) / range) * h;
      return `${x},${y}`;
    })
    .join(" ");

  const isUp = closes[closes.length - 1] >= closes[0];
  const color = isUp ? "#22c55e" : "#ef4444";

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-12" preserveAspectRatio="none">
      <defs>
        <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon
        points={`0,${h} ${points} ${w},${h}`}
        fill="url(#chartGrad)"
      />
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}