from uuid import uuid4

from app.schemas.job import JobCreateRequest, JobResponse, JobStatus


jobs: dict[str, JobResponse] = {}


def create_job(request: JobCreateRequest) -> JobResponse:
    job_id = str(uuid4())

    job = JobResponse(
        job_id=job_id,
        status=JobStatus.CREATED,
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