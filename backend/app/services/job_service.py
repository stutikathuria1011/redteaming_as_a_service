from uuid import uuid4

from app.schemas.job import (
    JobCreateRequest,
    JobProgress,
    JobResponse,
    JobStatus,
)


jobs: dict[str, JobResponse] = {}


def create_job(request: JobCreateRequest) -> JobResponse:
    job_id = str(uuid4())

    job = JobResponse(
        job_id=job_id,
        status=JobStatus.CREATED,
        target_name=request.model_name or request.target_url,
    )

    jobs[job_id] = job

    return job


def get_job(job_id: str) -> JobResponse | None:
    return jobs.get(job_id)


def update_job_status(
    job_id: str,
    status: JobStatus,
) -> None:

    job = jobs.get(job_id)

    if job is not None:
        job.status = status


def set_progress(job_id: str, done: int, total: int) -> None:
    job = jobs.get(job_id)

    if job is not None:
        job.progress = JobProgress(done=done, total=total)


def add_warning(job_id: str, message: str) -> None:
    job = jobs.get(job_id)

    if job is not None:
        job.warnings.append(message)


def set_error(job_id: str, message: str) -> None:
    job = jobs.get(job_id)

    if job is not None:
        job.error = message


def store_attacks(
    job_id: str,
    attacks,
) -> None:

    job = jobs.get(job_id)

    if job is not None:
        job.attacks = attacks


def store_results(
    job_id: str,
    results,
) -> None:

    job = jobs.get(job_id)

    if job is not None:
        job.results = results


def store_evaluations(
    job_id: str,
    evaluations,
) -> None:

    job = jobs.get(job_id)

    if job is not None:
        job.evaluations = evaluations


def store_report(
    job_id: str,
    report: dict,
    attack_success_rate: float | None = None,
    family_breakdown: dict | None = None,
) -> None:

    job = jobs.get(job_id)

    if job is not None:
        job.report = report
        job.attack_success_rate = attack_success_rate
        job.family_breakdown = family_breakdown


def store_execution_errors(
    job_id: str,
    errors: list[dict],
) -> None:

    job = jobs.get(job_id)

    if job is not None:
        job.execution_errors = errors