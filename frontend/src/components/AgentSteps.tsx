"use client";

import { useState } from "react";

interface Step {
  node: string;
  detail: string;
  status: string;
  decision?: string;
  action?: string;
  action_input?: Record<string, unknown>;
  observation?: string;
}

const NODE_LABELS: Record<string, string> = {
  context_loader: "加载上下文",
  intent_classifier: "意图识别",
  entity_resolver: "实体解析",
  planner: "制定计划",
  tool_executor: "执行工具",
  fallback_handler: "备选方案",
  evidence_validator: "证据验证",
  answer_composer: "生成回答",
  self_checker: "自检校验",
  safety_checker: "安全检查",
  context_writer: "保存上下文",
  fast_quote: "快速行情",
  fast_fundamentals: "快速基本面",
  fast_trend: "快速走势",
  fast_knowledge: "快速知识库",
  private_company_check: "非上市检查",
  missing_source_check: "来源检查",
};

export default function AgentSteps({
  steps,
  loading,
}: {
  steps: Step[];
  loading?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  if (steps.length === 0) return null;

  const lastStep = steps[steps.length - 1];
  const statusText = loading
    ? "RUNNING"
    : lastStep.status === "ok"
    ? "DONE"
    : lastStep.status === "error"
    ? "ERROR"
    : "CHECK";

  return (
    <div className="max-w-[92%]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-slate-500 transition-colors hover:text-slate-800"
      >
        <span className="font-mono text-accent-teal">{statusText}</span>
        <span>
          {loading
            ? `正在执行: ${NODE_LABELS[lastStep.node] || lastStep.node}`
            : `${steps.length} 个步骤完成`}
        </span>
        <svg
          className={`w-3 h-3 transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="m19 9-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="animate-fade-in mt-2 space-y-2 border-l border-surface-3 pl-3">
          {steps.map((step, i) => (
            <div key={i} className="flex items-start gap-2 text-[11px]">
              <span
                className={`mt-0.5 w-1.5 h-1.5 rounded-full shrink-0 ${
                  step.status === "ok"
                    ? "bg-accent-teal"
                    : step.status === "error"
                    ? "bg-accent-red"
                    : "bg-slate-500"
                }`}
              />
              <span className="flex-1 text-slate-400">
                <span className="font-mono text-slate-500">
                  {NODE_LABELS[step.node] || step.node}
                </span>
                {step.detail && (
                  <span className="ml-1.5 text-slate-600">{step.detail.slice(0, 80)}</span>
                )}
                {(step.decision || step.action || step.observation) && (
                  <div className="mt-1 space-y-0.5 text-[10px] leading-relaxed">
                    {step.decision && (
                      <div>
                        <span className="text-accent-gold/80">Decision</span>{" "}
                        <span className="text-slate-500">{step.decision}</span>
                      </div>
                    )}
                    {step.action && (
                      <div>
                        <span className="text-accent-teal/80">Action</span>{" "}
                        <code className="text-slate-400">{step.action}</code>
                        {step.action_input && (
                          <span className="text-slate-600">
                            ({JSON.stringify(step.action_input).slice(0, 120)})
                          </span>
                        )}
                      </div>
                    )}
                    {step.observation && (
                      <div>
                        <span className="text-brand-300/80">Observation</span>{" "}
                        <span className="text-slate-500">{step.observation.slice(0, 160)}</span>
                      </div>
                    )}
                  </div>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
