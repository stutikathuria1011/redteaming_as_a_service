from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.schemas.job import JobCreateRequest, JobResponse
from app.services.job_service import create_job, get_job
from app.services.run_service import run_job


router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"],
)


@router.post("", response_model=JobResponse)
async def create_new_job(
    request: JobCreateRequest,
    background_tasks: BackgroundTasks,
):
    job = create_job(request)

    background_tasks.add_task(
        run_job,
        job_id=job.job_id,
        model_name=request.model_name,
        target_url=request.target_url,
        api_key=request.api_key,
        number_of_attacks=request.number_of_attacks,
        attack_categories=request.attack_categories,
    )

    return job


@router.get("/{job_id}", response_model=JobResponse)
def get_existing_job(job_id: str):
    job = get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    return job