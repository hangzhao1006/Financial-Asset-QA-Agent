"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { askStream, SSEEvent, AskResponse } from "@/lib/api";
import ChatMessage from "@/components/ChatMessage";
import AgentSteps from "@/components/AgentSteps";
import SourceCards from "@/components/SourceCards";
import QuoteCard from "@/components/QuoteCard";
import AssetLookup from "@/components/AssetLookup";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: AskResponse;
  steps?: AskResponse["agent_steps"];
  loading?: boolean;
  error?: string;
}

const EXAMPLE_QUESTIONS = [
  "阿里巴巴当前股价是多少？",
  "TSLA 最近 7 天涨跌如何？",
  "什么是市盈率？",
  "收入和净利润的区别是什么？",
  "华为2025年报的业务亮点是什么？",
  "Apple 10-K 有哪些风险因素？",
];

function getOrCreateSessionId() {
  if (typeof window === "undefined") return "";
  const key = "finq_session_id";
  const existing = window.localStorage.getItem(key);
  if (existing) return existing;
  const created = `sess_${crypto.randomUUID()}`;
  window.localStorage.setItem(key, created);
  return created;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId] = useState(getOrCreateSessionId);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleSubmit = useCallback(
    async (question: string) => {
      if (!question.trim() || isStreaming) return;

      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content: question.trim(),
      };

      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "",
        steps: [],
        loading: true,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setInput("");
      setIsStreaming(true);

      try {
        for await (const event of askStream(question.trim(), sessionId)) {
          setMessages((prev) => {
            const updated = [...prev];
            const last = { ...updated[updated.length - 1] };

            if (event.event === "agent_step") {
              last.steps = [
                ...(last.steps || []),
                event.data as AskResponse["agent_steps"][number],
              ];
            } else if (event.event === "partial_answer") {
              last.content = (event.data as any).summary || "";
            } else if (event.event === "final_answer") {
              const resp = event.data as unknown as AskResponse;
              last.content = resp.summary;
              last.response = resp;
              last.loading = false;
            } else if (event.event === "error") {
              last.error = (event.data as any).message;
              last.loading = false;
            } else if (event.event === "done") {
              last.loading = false;
            }

            updated[updated.length - 1] = last;
            return updated;
          });
        }
      } catch (err: any) {
        setMessages((prev) => {
          const updated = [...prev];
          const last = { ...updated[updated.length - 1] };
          last.error = err.message || "Connection error";
          last.loading = false;
          updated[updated.length - 1] = last;
          return updated;
        });
      } finally {
        setIsStreaming(false);
      }
    },
    [isStreaming, sessionId]
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(input);
    }
  };

  return (
    <div className="market-grid min-h-screen">
      {/* Header */}
      <header className="border-b border-surface-3/80 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-5 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-brand-500/30 bg-brand-500/10 font-mono text-sm font-semibold text-brand-700">
            FQ
          </div>
          <div>
            <h1 className="font-display text-lg font-semibold tracking-tight text-slate-950">FinQ Terminal</h1>
            <p className="text-xs text-slate-500">
              Market data · Report RAG · Financial QA
            </p>
          </div>
          <div className="ml-auto hidden items-center gap-5 text-xs text-slate-500 sm:flex">
            <span className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-accent-green" />
              Fallback-ready
            </span>
            <span>Not investment advice</span>
          </div>
        </div>
      </header>

      <div className="mx-auto flex h-[calc(100vh-65px)] max-w-6xl gap-5 px-5 py-5">
        <aside className="hidden w-[340px] shrink-0 overflow-y-auto lg:block">
          <div className="mb-4">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
              Quick Asset
            </p>
            <AssetLookup />
          </div>

          <div className="panel px-4 py-4">
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
              Coverage
          </p>
            <div className="space-y-3 text-xs text-slate-400">
              <div className="flex items-center justify-between border-b border-surface-3 pb-2">
                <span>Market quote</span>
                <span className="font-mono text-accent-teal">live / demo</span>
              </div>
              <div className="flex items-center justify-between border-b border-surface-3 pb-2">
                <span>Financial reports</span>
                <span className="font-mono text-accent-teal">36 files</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Agent trace</span>
                <span className="font-mono text-accent-teal">ReAct</span>
              </div>
            </div>
          </div>
        </aside>

        <section className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-surface-3 bg-white/78">
          <main className="flex-1 overflow-y-auto px-4 py-5 sm:px-6">
            <div className="mx-auto max-w-3xl space-y-5">
              <div className="lg:hidden">
                <AssetLookup />
              </div>

              {messages.length === 0 && (
                <div className="animate-fade-in py-4 sm:py-8">
                  <div className="mb-8 border-b border-surface-3 pb-6">
                    <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-accent-teal">
                      Financial QA Workspace
                    </p>
                    <h2 className="mb-3 max-w-2xl text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">
                      查询行情、解释指标，并从财报中提取可引用证据。
                    </h2>
                    <p className="max-w-2xl text-sm leading-6 text-slate-400">
                      面向金融资产问答的轻量界面：左侧快速查资产，右侧进行多轮问答。系统会展示工具调用、来源和数据质量。
                    </p>
                  </div>

                  <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                    Try asking
                  </p>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {EXAMPLE_QUESTIONS.map((q) => (
                      <button
                        key={q}
                        onClick={() => handleSubmit(q)}
                        className="panel-soft group px-4 py-3 text-left text-sm text-slate-700 transition-colors hover:border-brand-500/40 hover:bg-surface-2"
                      >
                        <span className="mr-2 font-mono text-xs text-accent-teal">↳</span>
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((msg) => (
                <div key={msg.id} className="animate-slide-up">
                  {msg.role === "user" ? (
                    <div className="flex justify-end">
                      <div className="max-w-[78%] rounded-xl border border-brand-500/25 bg-brand-500/10 px-4 py-3 text-sm leading-6 text-slate-900">
                        {msg.content}
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-col gap-3">
                      {/* Agent steps indicator */}
                      {msg.steps && msg.steps.length > 0 && (
                        <AgentSteps steps={msg.steps} loading={msg.loading} />
                      )}

                      {/* Loading state */}
                      {msg.loading && !msg.content && (
                        <div className="panel-soft max-w-[82%] px-4 py-3">
                          <div className="flex items-center gap-2 text-sm text-slate-400">
                            <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-surface-4 border-t-accent-teal" />
                            <span>分析中</span>
                            <span className="typing-dots" />
                          </div>
                        </div>
                      )}

                      {/* Error */}
                      {msg.error && (
                        <div className="panel-soft max-w-[82%] border-accent-red/30 px-4 py-3">
                          <p className="text-sm text-accent-red">Error: {msg.error}</p>
                        </div>
                      )}

                      {/* Answer */}
                      {msg.content && (
                        <ChatMessage content={msg.content} response={msg.response} />
                      )}

                      {/* Quote card for market data */}
                      {msg.response?.objective_data &&
                        Object.keys(msg.response.objective_data).length > 0 && (
                          <QuoteCard data={msg.response.objective_data} />
                        )}

                      {/* Sources */}
                      {msg.response?.sources && msg.response.sources.length > 0 && (
                        <SourceCards sources={msg.response.sources} />
                      )}
                    </div>
                  )}
                </div>
              ))}

              <div ref={bottomRef} />
            </div>
          </main>

          {/* Input area */}
          <footer className="border-t border-surface-3 bg-white/80 px-4 py-4">
            <div className="mx-auto max-w-3xl">
              <div className="flex items-end gap-2 rounded-xl border border-surface-3 bg-white px-3 py-2 shadow-sm focus-within:border-brand-500/60">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask about prices, ratios, reports..."
                  rows={1}
                  className="max-h-32 flex-1 resize-none bg-transparent py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400"
                  disabled={isStreaming}
                />
                <button
                  onClick={() => handleSubmit(input)}
                  disabled={!input.trim() || isStreaming}
                  className="shrink-0 rounded-lg bg-brand-600 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-brand-500 disabled:cursor-not-allowed disabled:opacity-30"
                >
                  Send
                </button>
              </div>
              <p className="mt-2 text-center text-[10px] text-slate-600">
                AKShare / Yahoo Finance · Chroma RAG · For research only
              </p>
            </div>
          </footer>
        </section>
      </div>
    </div>
  );
}