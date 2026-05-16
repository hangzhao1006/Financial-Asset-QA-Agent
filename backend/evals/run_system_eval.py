"""Run a lightweight end-to-end evaluation for the Financial QA system.

This script is intentionally practical for demos:
- It does not require the FastAPI server to be running.
- It calls the agent directly.
- It produces a JSON report under backend/evals/reports/.
- It checks market answers, knowledge answers, and session-memory follow-ups.

Run from the project root:
    source backend/.venv/bin/activate
    python backend/evals/run_system_eval.py
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import os
import sys
import warnings
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4


os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY", "False")
os.environ.setdefault("DO_NOT_TRACK", "1")

logging.basicConfig(level=logging.ERROR)
for noisy_logger in ("chromadb", "posthog", "yfinance", "urllib3", "backend.app.services.market_data"):
    logging.getLogger(noisy_logger).setLevel(logging.ERROR)
warnings.filterwarnings("ignore")
if os.getenv("EVAL_VERBOSE") != "1":
    logging.disable(logging.CRITICAL)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.agent.graph import run_agent  # noqa: E402


DATASET_PATH = PROJECT_ROOT / "backend" / "evals" / "rag_eval_dataset.json"
REPORT_DIR = PROJECT_ROOT / "backend" / "evals" / "reports"


@dataclass
class EvalCaseResult:
    question: str
    expected_intent: str
    answer_type: str
    passed: bool
    latency_ms: int
    summary: str
    checks: dict
    warnings: list[str]


def _load_dataset() -> list[dict]:
    with DATASET_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(k.lower() in lowered for k in keywords)


def _is_error_answer(text: str) -> bool:
    return _contains_any(text, [
        "抱歉，生成回答时出现错误",
        "connection error",
        "unable to generate",
        "error:",
    ])


def _keyword_coverage(answer: str, ground_truth: str) -> float:
    """Simple lexical coverage for Chinese/English finance keywords."""
    candidates = [
        "市盈率", "p/e", "eps", "每股收益", "收入", "净利润", "top line", "bottom line",
        "自由现金流", "经营活动现金流", "资本支出", "牛市", "熊市", "20%",
        "毛利率", "营业收入", "营业成本", "贝塔", "beta", "波动",
    ]
    expected = [kw for kw in candidates if kw.lower() in ground_truth.lower()]
    if not expected:
        return 1.0
    hits = [kw for kw in expected if kw.lower() in answer.lower()]
    return len(hits) / len(expected)


def _check_case(sample: dict, response) -> tuple[bool, dict]:
    intent = sample.get("intent", "")
    summary = response.summary or ""
    objective = response.objective_data or {}
    checks: dict = {}

    if intent == "knowledge":
        checks["answer_type_is_knowledge"] = response.answer_type == "knowledge"
        checks["has_summary"] = len(summary.strip()) >= 20
        checks["not_error_answer"] = not _is_error_answer(summary)
        checks["not_market_only"] = not objective.get("price")
        checks["keyword_coverage"] = _keyword_coverage(summary + " " + response.analysis, sample.get("ground_truth", "")) >= 0.5
        return all(checks.values()), checks

    if intent == "market_quote":
        checks["answer_type_is_market"] = response.answer_type == "market"
        checks["not_error_answer"] = not _is_error_answer(summary)
        checks["has_price"] = objective.get("price") is not None
        checks["has_symbol"] = bool(objective.get("symbol"))
        checks["no_analysis_required"] = response.analysis == ""
        return all(checks.values()), checks

    if intent == "market_trend":
        checks["answer_type_is_market"] = response.answer_type == "market"
        checks["not_error_answer"] = not _is_error_answer(summary)
        checks["mentions_trend_or_return"] = _contains_any(
            summary + " " + response.analysis,
            ["涨", "跌", "震荡", "trend", "return", "%"],
        )
        return all(checks.values()), checks

    checks["has_summary"] = bool(summary.strip())
    return all(checks.values()), checks


async def _run_quiet(coro):
    """Suppress noisy third-party stdout/stderr during eval runs."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        return await coro


async def _eval_dataset_cases() -> list[EvalCaseResult]:
    results: list[EvalCaseResult] = []
    for sample in _load_dataset():
        session_id = f"eval_{uuid4()}"
        start = perf_counter()
        response = await _run_quiet(run_agent(sample["question"], session_id=session_id))
        latency_ms = int((perf_counter() - start) * 1000)
        passed, checks = _check_case(sample, response)
        results.append(EvalCaseResult(
            question=sample["question"],
            expected_intent=sample.get("intent", ""),
            answer_type=response.answer_type,
            passed=passed,
            latency_ms=latency_ms,
            summary=response.summary,
            checks=checks,
            warnings=response.warnings,
        ))
    return results


async def _eval_followup_memory() -> EvalCaseResult:
    session_id = f"eval_followup_{uuid4()}"
    await _run_quiet(run_agent("阿里巴巴当前股价是多少？", session_id=session_id))

    start = perf_counter()
    response = await _run_quiet(run_agent("他的市盈率呢？", session_id=session_id))
    latency_ms = int((perf_counter() - start) * 1000)

    objective = response.objective_data or {}
    checks = {
        "memory_used": response.memory_used is True,
        "symbol_is_baba": objective.get("symbol") == "BABA",
        "has_pe_ratio": objective.get("pe_ratio") is not None,
        "not_generic_pe_definition": response.answer_type == "market",
    }

    return EvalCaseResult(
        question="FOLLOWUP: 阿里巴巴当前股价是多少？ -> 他的市盈率呢？",
        expected_intent="market_fundamental_followup",
        answer_type=response.answer_type,
        passed=all(checks.values()),
        latency_ms=latency_ms,
        summary=response.summary,
        checks=checks,
        warnings=response.warnings,
    )


async def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    case_results = await _eval_dataset_cases()
    case_results.append(await _eval_followup_memory())

    total = len(case_results)
    passed = sum(1 for r in case_results if r.passed)
    avg_latency = int(sum(r.latency_ms for r in case_results) / max(total, 1))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / max(total, 1), 3),
            "avg_latency_ms": avg_latency,
        },
        "results": [asdict(r) for r in case_results],
    }

    out_path = REPORT_DIR / "system_eval_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Report written to: {out_path}")
    if passed != total:
        print("\nFailed cases:")
        for result in case_results:
            if not result.passed:
                print(f"- {result.question}")
                print(f"  checks={result.checks}")
                print(f"  summary={result.summary[:160]}")


if __name__ == "__main__":
    asyncio.run(main())
