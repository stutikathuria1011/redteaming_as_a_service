from app.schemas.evaluation import AttackResult, EvaluationResult


async def evaluate_attack(
    attack_result: AttackResult,
) -> EvaluationResult:

    # Temporary mock evaluator.
    # This will later be replaced by the real evaluator service.

    return EvaluationResult(
        attack_id=attack_result.attack_id,
        score=0,
        severity="LOW",
        successful=False,
        finding="Mock evaluation - no vulnerability detected.",
        reason="Temporary evaluator used for backend integration testing.",
    )