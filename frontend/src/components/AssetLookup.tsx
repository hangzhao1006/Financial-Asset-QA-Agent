"use client";

import { useState, useCallback, useEffect } from "react";
import {
  fetchQuote,
  fetchIntraday,
  fetchHistory,
  resolveAsset,
  QuoteData,
  IntradayData,
  HistoryData,
  ResolveData,
} from "@/lib/api";

interface AssetState {
  resolve: ResolveData | null;
  quote: QuoteData | null;
  intraday: IntradayData | null;
  history7d: HistoryData | null;
  history30d: HistoryData | null;
  loading: boolean;
  error: string | null;
}

const QUICK_ASSETS = ["BABA", "TSLA", "AAPL", "NVDA", "茅台", "腾讯"];

export default function AssetLookup() {
  const [query, setQuery] = useState("BABA");
  const [chartRange, setChartRange] = useState<"intraday" | "7d" | "30d">("intraday");
  const [asset, setAsset] = useState<AssetState>({
    resolve: null,
    quote: null,
    intraday: null,
    history7d: null,
    history30d: null,
    loading: false,
    error: null,
  });

  const lookup = useCallback(async (q: string) => {
    if (!q.trim()) return;
    setChartRange("intraday");
    setAsset({
      resolve: null,
      quote: null,
      intraday: null,
      history7d: null,
      history30d: null,
      loading: true,
      error: null,
    });

    try {
      const resolved = await resolveAsset(q.trim());
      setAsset(prev => ({ ...prev, resolve: resolved }));

      const [quoteRes, intradayRes, history7dRes, history30dRes] = await Promise.allSettled([
        fetchQuote(resolved.symbol),
        fetchIntraday(resolved.symbol),
        fetchHistory(resolved.symbol, "7d"),
        fetchHistory(resolved.symbol, "30d"),
      ]);
      const quote = quoteRes.status === "fulfilled" ? quoteRes.value : null;
      const intraday = intradayRes.status === "fulfilled" ? intradayRes.value : null;
      const history7d = history7dRes.status === "fulfilled" ? history7dRes.value : null;
      const history30d = history30dRes.status === "fulfilled" ? history30dRes.value : null;
      const failures = [
        quoteRes.status === "rejected" ? "quote" : null,
        intradayRes.status === "rejected" ? "intraday" : null,
        history7dRes.status === "rejected" ? "7d history" : null,
        history30dRes.status === "rejected" ? "30d history" : null,
      ].filter(Boolean);

      setAsset(prev => ({
        ...prev,
        quote,
        intraday,
        history7d,
        history30d,
        loading: false,
        error: !quote && !intraday && !history7d && !history30d
          ? `行情查询失败: ${failures.join(", ") || "unknown"}`
          : null,
      }));
    } catch (err: unknown) {
      setAsset(prev => ({
        ...prev,
        loading: false,
        error: err instanceof Error ? err.message : "查询失败",
      }));
    }
  }, []);

  useEffect(() => {
    lookup("BABA");
  }, [lookup]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") lookup(query);
  };

  return (
    <div className="w-full max-w-2xl mx-auto">
      {/* Search bar */}
      <div className="panel mb-4 flex items-center gap-2 px-4 py-3">
        <svg className="h-4 w-4 shrink-0 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-6-6m2-5a7 7 0 1 1-14 0 7 7 0 0 1 14 0z" />
        </svg>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入股票代码或公司名称，如 BABA、阿里巴巴、茅台..."
          className="flex-1 bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
        />
        <button
          onClick={() => lookup(query)}
          disabled={asset.loading || !query.trim()}
          className="rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-brand-500 disabled:opacity-30"
        >
          查询
        </button>
      </div>

      {/* Quick buttons */}
      <div className="flex flex-wrap gap-2 mb-4">
        {QUICK_ASSETS.map((s) => (
          <button
            key={s}
            onClick={() => { setQuery(s); lookup(s); }}
            className="rounded-full border border-surface-3 bg-white px-3 py-1 text-[11px] text-slate-500 transition-colors hover:border-brand-500/40 hover:text-brand-700"
          >
            {s}
          </button>
        ))}
      </div>

      {/* Loading */}
      {asset.loading && (
        <div className="panel px-5 py-6 text-center">
          <span className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-surface-3 border-t-accent-teal" />
          <p className="mt-2 text-sm text-slate-500">正在获取行情数据...</p>
        </div>
      )}

      {/* Error */}
      {asset.error && (
        <div className="panel border-accent-red/30 px-5 py-4">
          <p className="text-sm text-accent-red">Error: {asset.error}</p>
        </div>
      )}

      {/* Result card */}
      {!asset.loading && asset.resolve && (asset.quote || asset.intraday || asset.history7d || asset.history30d) && (
        <div className="panel animate-slide-up px-5 py-5">
          {/* Header */}
          <div className="flex items-start justify-between mb-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="rounded bg-brand-500/10 px-2 py-0.5 font-mono text-sm text-brand-700">
                  {asset.resolve.symbol}
                </span>
                <span className="rounded bg-surface-2 px-2 py-0.5 text-xs text-slate-500">
                  {asset.resolve.market.toUpperCase()}
                </span>
              </div>
              <p className="text-sm text-slate-500">{asset.resolve.name}</p>
            </div>
            <div className="text-right">
              {(asset.quote?.price ?? asset.intraday?.current_price) != null && (
                <p className="font-display text-2xl font-semibold text-slate-950">
                  {(asset.quote?.currency ?? asset.intraday?.currency) === "CNY" ? "¥" : (asset.quote?.currency ?? asset.intraday?.currency) === "HKD" ? "HK$" : "$"}
                  {(asset.quote?.price ?? asset.intraday?.current_price)?.toFixed(2)}
                </p>
              )}
              {asset.intraday?.change_pct != null && (
                <p className={`text-sm font-medium ${
                  asset.intraday.change_pct > 0 ? "text-brand-500" :
                  asset.intraday.change_pct < 0 ? "text-accent-red" : "text-slate-500"
                }`}>
                  {asset.intraday.change_pct > 0 ? "+" : ""}
                  {asset.intraday.change_pct.toFixed(2)}%
                </p>
              )}
            </div>
          </div>

          {/* Chart range tabs */}
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex rounded-lg border border-surface-3 bg-surface-2 p-1">
              {[
                { key: "intraday", label: "日内" },
                { key: "7d", label: "7日" },
                { key: "30d", label: "30日" },
              ].map((item) => (
                <button
                  key={item.key}
                  onClick={() => setChartRange(item.key as "intraday" | "7d" | "30d")}
                  className={`rounded-md px-3 py-1 text-[11px] font-medium transition-colors ${
                    chartRange === item.key
                      ? "bg-white text-brand-700 shadow-sm"
                      : "text-slate-500 hover:text-slate-900"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <TrendSummary
              data={chartRange === "7d" ? asset.history7d : chartRange === "30d" ? asset.history30d : null}
            />
          </div>

          {chartRange === "intraday" && asset.intraday && asset.intraday.data.length > 1 && (
            <IntradayChart data={asset.intraday.data} currency={asset.quote?.currency ?? asset.intraday.currency} />
          )}
          {chartRange === "intraday" && asset.intraday && asset.intraday.data.length <= 1 && (
            <div className="rounded-xl border border-surface-3 px-4 py-6 text-center text-xs text-slate-500">
              暂无足够日内数据绘制走势图
            </div>
          )}
          {chartRange === "intraday" && !asset.intraday && (
            <EmptyChartState label="暂无日内走势数据" />
          )}

          {chartRange === "7d" && asset.history7d && asset.history7d.data.length > 1 && (
            <HistoryChart data={asset.history7d.data} currency={asset.history7d.currency} />
          )}
          {chartRange === "7d" && (!asset.history7d || asset.history7d.data.length <= 1) && (
            <EmptyChartState label="暂无足够 7 日走势数据" />
          )}

          {chartRange === "30d" && asset.history30d && asset.history30d.data.length > 1 && (
            <HistoryChart data={asset.history30d.data} currency={asset.history30d.currency} />
          )}
          {chartRange === "30d" && (!asset.history30d || asset.history30d.data.length <= 1) && (
            <EmptyChartState label="暂无足够 30 日走势数据" />
          )}

          {/* Footer info */}
          <div className="mt-3 flex items-center gap-4 text-[10px] text-slate-500">
            <span>数据来源: {asset.quote?.provider ?? asset.intraday?.provider ?? "unknown"}</span>
            {asset.quote?.timestamp && (
              <span>{new Date(asset.quote.timestamp).toLocaleTimeString("zh-CN")}</span>
            )}
            {asset.intraday?.warnings.map((w, i) => (
              <span key={i} className="text-accent-gold">{w}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TrendSummary({ data }: { data: HistoryData | null }) {
  if (!data || data.return_pct == null) {
    return <span className="text-[11px] text-slate-400">选择区间查看趋势</span>;
  }

  const isPositive = data.return_pct > 0;
  const isNegative = data.return_pct < 0;
  return (
    <div className="text-right text-[11px]">
      <span
        className={`font-mono font-medium ${
          isPositive ? "text-brand-600" : isNegative ? "text-accent-red" : "text-slate-500"
        }`}
      >
        {isPositive ? "+" : ""}
        {data.return_pct.toFixed(2)}%
      </span>
      {data.trend && <span className="ml-2 text-slate-500">{data.trend}</span>}
    </div>
  );
}

function EmptyChartState({ label }: { label: string }) {
  return (
    <div className="rounded-xl border border-surface-3 px-4 py-8 text-center text-xs text-slate-500">
      {label}
    </div>
  );
}

function IntradayChart({ data, currency }: { data: Array<{ time: string; price: number }>; currency: string }) {
  const prices = data.map(d => d.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const w = 560;
  const h = 120;
  const padY = 10;

  const points = prices
    .map((p, i) => {
      const x = (i / (prices.length - 1)) * w;
      const y = padY + (h - 2 * padY) - ((p - min) / range) * (h - 2 * padY);
      return `${x},${y}`;
    })
    .join(" ");

  const isUp = prices[prices.length - 1] >= prices[0];
  const color = isUp ? "#22c55e" : "#ef4444";
  const currSign = currency === "CNY" ? "¥" : currency === "HKD" ? "HK$" : "$";

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-28" preserveAspectRatio="none">
        <defs>
          <linearGradient id="intradayGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.2" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={`0,${h} ${points} ${w},${h}`} fill="url(#intradayGrad)" />
        <polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <div className="mt-1 flex justify-between px-1 text-[10px] text-slate-500">
        <span>{data[0].time}</span>
        <span>最高 {currSign}{max.toFixed(2)} · 最低 {currSign}{min.toFixed(2)}</span>
        <span>{data[data.length - 1].time}</span>
      </div>
    </div>
  );
}

function HistoryChart({ data, currency }: { data: Array<{ date: string; close: number }>; currency: string }) {
  const prices = data.map(d => d.close);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const w = 560;
  const h = 120;
  const padY = 10;

  const points = prices
    .map((p, i) => {
      const x = (i / (prices.length - 1)) * w;
      const y = padY + (h - 2 * padY) - ((p - min) / range) * (h - 2 * padY);
      return `${x},${y}`;
    })
    .join(" ");

  const isUp = prices[prices.length - 1] >= prices[0];
  const color = isUp ? "#0891b2" : "#ef4444";
  const currSign = currency === "CNY" ? "¥" : currency === "HKD" ? "HK$" : "$";

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${w} ${h}`} className="h-28 w-full" preserveAspectRatio="none">
        <defs>
          <linearGradient id="historyGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.16" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={`0,${h} ${points} ${w},${h}`} fill="url(#historyGrad)" />
        <polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <div className="mt-1 flex justify-between px-1 text-[10px] text-slate-500">
        <span>{data[0].date}</span>
        <span>最高 {currSign}{max.toFixed(2)} · 最低 {currSign}{min.toFixed(2)}</span>
        <span>{data[data.length - 1].date}</span>
      </div>
    </div>
  );
}