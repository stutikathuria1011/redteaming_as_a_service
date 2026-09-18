from uuid import uuid4

from app.schemas.job import JobCreateRequest, JobResponse, JobStatus


def create_job(request: JobCreateRequest) -> JobResponse:
    job_id = str(uuid4())

    # Attack generator integration will be added here later.
    # Evaluator integration will also be added later.

    return JobResponse(
        job_id=job_id,
        status=JobStatus.CREATED,
    )