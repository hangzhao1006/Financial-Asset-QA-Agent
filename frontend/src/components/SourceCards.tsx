"use client";

interface Source {
  type: string;
  title?: string;
  raw_title?: string;
  source_file?: string;
  url?: string;
  urls?: string[];
  section?: string;
  score?: number;
}

export default function SourceCards({ sources }: { sources: Source[] }) {
  if (!sources.length) return null;

  return (
    <div className="max-w-[92%]">
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
        参考来源
      </p>
      <div className="flex flex-wrap gap-2">
        {sources.map((src, i) => (
          <div
            key={i}
            className="flex max-w-xs items-center gap-2 rounded-lg border border-surface-3 bg-white px-3 py-2 text-[11px]"
          >
            <span
              className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                src.type === "news"
                  ? "bg-accent-blue"
                  : "bg-accent-gold"
              }`}
            />
            <div className="min-w-0">
              <p className="truncate text-slate-700">
                {formatSourceTitle(src)}
              </p>
              {(src.url || src.urls?.[0]) && (
                <a
                  href={src.url || src.urls?.[0]}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block truncate text-accent-blue/80 hover:text-accent-blue"
                >
                  {formatSourceHost(src.url || src.urls?.[0] || "")}
                </a>
              )}
              {src.score != null && (
                <span className="text-slate-500">
                  score: {(src.score * 100).toFixed(0)}%
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatSourceTitle(src: Source) {
  const title = src.title || src.section || src.type;
  if (title === "demo") return "本地演示数据";
  if (title === "none") return "暂无外部数据源";
  return title;
}

function formatSourceHost(url: string) {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}
