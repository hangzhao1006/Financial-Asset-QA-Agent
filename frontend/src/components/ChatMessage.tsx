"use client";

import { AskResponse } from "@/lib/api";

interface Props {
  content: string;
  response?: AskResponse;
}

function renderMarkdown(text: string): string {
  return text
    .replace(/### (.+)/g, '<h3>$1</h3>')
    .replace(/## (.+)/g, '<h3>$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n- /g, '\n• ')
    .replace(/\n/g, '<br/>');
}

export default function ChatMessage({ content, response }: Props) {
  const qualityColor =
    response?.data_quality === "high"
      ? "text-accent-green"
      : response?.data_quality === "medium"
      ? "text-accent-gold"
      : "text-slate-500";

  return (
    <div className="panel max-w-[92%] px-5 py-4">
      <div
        className="answer-content text-sm leading-relaxed"
        dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
      />

      {response?.analysis && (
        <div className="mt-4 border-t border-surface-3 pt-3">
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
            分析
          </p>
          <p className="text-sm leading-relaxed text-slate-400">{response.analysis}</p>
        </div>
      )}

      {response && (
        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-surface-3 pt-3 text-[11px] text-slate-500">
          <span className="flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full ${qualityColor.replace("text-", "bg-")}`} />
            {response.data_quality || "—"}
          </span>
          <span className="font-mono">{response.answer_type}</span>
          {response.cache_hit && <span className="text-accent-gold">cached</span>}
          {response.memory_used && <span>memory</span>}
          {response.warnings.length > 0 && (
            <span className="text-accent-red">warnings {response.warnings.length}</span>
          )}
        </div>
      )}
    </div>
  );
}
