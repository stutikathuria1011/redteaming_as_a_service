from app.schemas.attack import AttackGenerationRequest
from app.schemas.evaluation import AttackResult, EvaluationResult
from app.schemas.job import JobStatus

from app.services.generator_service import generate_attacks
from app.services.target_service import send_attack
from app.services.evaluator_service import evaluate_attack
from app.services.job_service import (
    update_job_status,
    store_attacks,
    store_results,
    store_evaluations,
)


async def run_job(
    job_id: str,
    model_name: str,
    target_url: str,
    api_key: str,
    number_of_attacks: int,
    attack_categories: list[str],
) -> list[EvaluationResult]:

    try:

        # 1. Generate attacks
        update_job_status(
            job_id,
            JobStatus.GENERATING,
        )

        generation_request = AttackGenerationRequest(
            job_id=job_id,
            model_name=model_name,
            attack_categories=attack_categories,
            number_of_attacks=number_of_attacks,
        )

        generated = await generate_attacks(
            generation_request
        )

        store_attacks(
            job_id,
            generated.attacks,
        )

        # 2. Execute attacks against target
        update_job_status(
            job_id,
            JobStatus.EXECUTING,
        )

        results = []

        for attack in generated.attacks:

            target_response = await send_attack(
                target_url=target_url,
                api_key=api_key,
                model_name=model_name,
                prompt=attack.prompt,
            )

            attack_result = AttackResult(
                attack_id=attack.attack_id,
                category=attack.category,
                prompt=attack.prompt,
                target_response=target_response,
            )

            results.append(attack_result)

        store_results(
            job_id,
            results,
        )

        # 3. Evaluate attack + target response
        update_job_status(
            job_id,
            JobStatus.EVALUATING,
        )

        evaluations = []

        for attack_result in results:

            evaluation = await evaluate_attack(
                attack_result
            )

            evaluations.append(evaluation)

        store_evaluations(
            job_id,
            evaluations,
        )

        # 4. Mark job as completed
        update_job_status(
            job_id,
            JobStatus.COMPLETED,
        )

        return evaluations

    except Exception:

        update_job_status(
            job_id,
            JobStatus.FAILED,
        )

        raise