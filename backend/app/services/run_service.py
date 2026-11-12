import logging
import os

from app.schemas.attack import AttackGenerationRequest
from app.schemas.evaluation import AttackResult
from app.schemas.job import JobStatus

from app.services.generator_service import generate_attacks
from app.services.target_service import send_attack
from app.services.evaluator_service import evaluate_run
from app.services.report_service import family_breakdown, safe_success_rate

from app.services.job_service import (
    add_warning,
    set_error,
    set_progress,
    update_job_status,
    store_attacks,
    store_results,
    store_evaluations,
    store_report,
    store_execution_errors,
)

logger = logging.getLogger(__name__)

# The judge's free Groq quota fits about 100 pairs a day (130-200 at the very best).
JUDGE_SOFT_LIMIT = int(os.getenv("JUDGE_SOFT_LIMIT", "150"))


async def run_job(
    job_id: str,
    model_name: str,
    target_url: str,
    api_key: str,
    number_of_attacks: int,
    attack_categories: list[str],
    system_prompt: str | None = None,
):

    try:
        if number_of_attacks > JUDGE_SOFT_LIMIT:
            add_warning(
                job_id,
                f"{number_of_attacks} attacks is above ~{JUDGE_SOFT_LIMIT}, about what the "
                "judge's free Groq quota covers per day. Pairs past the quota come back "
                "UNSCORED (excluded from the success rate, not counted as safe).",
            )

        # 1. Generate attacks
        update_job_status(job_id, JobStatus.GENERATING)

        generation_request = AttackGenerationRequest(
            job_id=job_id,
            model_name=model_name,
            attack_categories=attack_categories,
            number_of_attacks=number_of_attacks,
        )

        generated = await generate_attacks(generation_request)

        if len(generated.attacks) < number_of_attacks:
            add_warning(
                job_id,
                f"Only {len(generated.attacks)} of {number_of_attacks} requested attacks "
                "exist for the chosen categories.",
            )

        store_attacks(job_id, generated.attacks)

        # 2. Execute attacks against target
        update_job_status(job_id, JobStatus.EXECUTING)

        total = len(generated.attacks)
        set_progress(job_id, 0, total)

        results = []
        execution_errors = []

        for done, attack in enumerate(generated.attacks, start=1):

            # The target's own system prompt (if the user gave one) wins; otherwise the
            # attack's built-in scenario. The judge gets exactly what the target saw.
            context = system_prompt or attack.system_context

            try:
                target_response = await send_attack(
                    target_url=target_url,
                    api_key=api_key,
                    model_name=model_name,
                    prompt=attack.prompt,
                    system_context=context,
                )

                attack_result = AttackResult(
                    attack_id=attack.attack_id,
                    category=attack.category,
                    prompt=attack.prompt,
                    target_response=target_response,
                    system_context=context,
                )

                results.append(attack_result)

            except Exception as exc:

                execution_errors.append({
                    "attack_id": attack.attack_id,
                    "category": attack.category,
                    "error": f"{type(exc).__name__}: {exc}",
                })

            set_progress(job_id, done, total)

        store_results(job_id, results)
        store_execution_errors(job_id, execution_errors)

        if execution_errors:
            add_warning(
                job_id,
                f"{len(execution_errors)} of {total} attacks got no usable answer from the "
                "target. See execution_errors; they were not sent to the judge.",
            )

        # An empty run must not look like a clean one.
        if not results:
            first = execution_errors[0]["error"] if execution_errors else "n/a"
            raise RuntimeError(
                f"The target gave no usable answer to any attack. First error: {first}"
            )

        # 3. Evaluate: ONE judge call for the whole run. It judges every pair and builds
        #    the report in the same pass; never also judge per attack (double cost).
        update_job_status(job_id, JobStatus.EVALUATING)

        set_progress(job_id, 0, len(results))

        evaluations, report = await evaluate_run(
            results,
            on_progress=lambda done, total: set_progress(job_id, done, total),
        )

        store_evaluations(job_id, evaluations)

        store_report(
            job_id,
            report,
            attack_success_rate=safe_success_rate(report),
            family_breakdown=family_breakdown(generated.attacks, evaluations),
        )

        unscored = sum(1 for e in evaluations if e.score is None)

        if unscored == len(evaluations):
            add_warning(
                job_id,
                "No pair could be scored (check the judge API key and quota). "
                "There is no attack success rate for this run.",
            )
        elif unscored:
            add_warning(
                job_id,
                f"{unscored} of {len(evaluations)} pairs could not be scored (see "
                "report.errors). They are excluded from the success rate, not counted as safe.",
            )

        # 4. Complete job
        update_job_status(job_id, JobStatus.COMPLETED)

    except Exception as exc:

        logger.exception("Job %s failed", job_id)

        set_error(job_id, f"{type(exc).__name__}: {exc}"[:500])

        update_job_status(job_id, JobStatus.FAILED)