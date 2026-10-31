import asyncio
import time

from analysis import make_report
from judge import judge
from report import SEVERITY_LABELS, SUCCESS_THRESHOLD, build_report


def _get(obj, key):
    return obj[key] if isinstance(obj, dict) else getattr(obj, key)


def judge_pair(attack_result):
    """Judge one AttackResult (dict or object) and return its fields merged with the verdict."""
    verdict = judge(_get(attack_result, "prompt"), _get(attack_result, "target_response"))
    return {
        "attack_id": _get(attack_result, "attack_id"),
        "category": _get(attack_result, "category"),
        "prompt": _get(attack_result, "prompt"),
        "target_response": _get(attack_result, "target_response"),
        **verdict,
    }


def to_evaluation(row):
    """Map a judged row to the fields of backend's EvaluationResult, plus an error field.

    An unscored pair gets score None and severity UNSCORED, never a safe-looking value.
    """
    score = row["severity_score"]
    if score is None:
        return {
            "attack_id": row["attack_id"],
            "score": None,
            "severity": "UNSCORED",
            "successful": False,
            "finding": "Not scored",
            "reason": row["reason"],
            "error": row["reason"],
        }
    return {
        "attack_id": row["attack_id"],
        "score": float(score),
        "severity": SEVERITY_LABELS[score],
        "successful": score >= SUCCESS_THRESHOLD,
        "finding": row["finding"],
        "reason": row["reason"],
        "error": None,
    }


def evaluate(attack_result):
    """Blocking: judge one AttackResult and return EvaluationResult fields as a dict."""
    return to_evaluation(judge_pair(attack_result))


async def evaluate_async(attack_result):
    """Async wrapper so FastAPI is not blocked while the judge calls the API."""
    return await asyncio.to_thread(evaluate, attack_result)


def run_judge(attack_results, pause=0.5, on_progress=None, analysis=True):
    """Judge a whole run and build the report.

    Returns {"evaluations": [...], "report": {...}}. on_progress(done, total) is called after each pair.
    """
    attack_results = list(attack_results)
    rows = []
    for i, attack_result in enumerate(attack_results, 1):
        rows.append(judge_pair(attack_result))
        if on_progress:
            on_progress(i, len(attack_results))
        time.sleep(pause)
    report = make_report(rows) if analysis else build_report(rows)
    return {"evaluations": [to_evaluation(r) for r in rows], "report": report}
