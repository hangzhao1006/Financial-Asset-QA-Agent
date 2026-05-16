"""RAGAS evaluation wrapper."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def evaluate_rag(
    questions: list[str],
    answers: list[str],
    contexts: list[list[str]],
    ground_truths: list[str],
) -> dict:
    """Run RAGAS evaluation on a test set. Returns metric scores."""
    try:
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
        from datasets import Dataset

        ds = Dataset.from_dict({
            "question": questions,
            "answer": answers,
            "contexts": contexts,
            "ground_truth": ground_truths,
        })

        result = evaluate(
            ds,
            metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        )
        return dict(result)
    except ImportError as exc:
        logger.error("RAGAS or datasets not installed: %s", exc)
        return {"error": "RAGAS not installed"}
    except Exception as exc:
        logger.error("RAGAS evaluation failed: %s", exc)
        return {"error": str(exc)}
