"""Small pure helpers around the judge's report. No judge imports."""
from collections import defaultdict
from typing import Optional

from app.schemas.attack import GeneratedAttack
from app.schemas.evaluation import EvaluationResult


def safe_success_rate(report: dict) -> Optional[float]:
    """Attack success rate, or None when nothing was scored.

    The judge says a rate means nothing unless report["summary"]["scored"] > 0.
    The UI must show "no result" for None, never 0%.
    """
    summary = report.get("summary", {})

    if summary.get("scored", 0) > 0:
        return summary.get("attack_success_rate")

    return None


def family_breakdown(
    attacks: list[GeneratedAttack],
    evaluations: list[EvaluationResult],
) -> dict[str, dict]:
    """Success rate per mutation family. Unscored pairs are excluded, never counted
    as safe. Compare each family with "original" to see what mutation adds."""
    family_of = {a.attack_id: a.family or "unknown" for a in attacks}
    counts = defaultdict(lambda: {"scored": 0, "successful": 0})

    for e in evaluations:
        if e.score is None:
            continue
        row = counts[family_of.get(e.attack_id, "unknown")]
        row["scored"] += 1
        row["successful"] += int(e.successful)

    return {
        family: {**row, "success_rate": round(row["successful"] / row["scored"], 3)}
        for family, row in sorted(counts.items())
    }