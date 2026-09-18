from fastapi import APIRouter

from app.schemas.job import JobCreateRequest, JobResponse
from app.services.job_service import create_job


router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"],
)


@router.post("", response_model=JobResponse)
def create_new_job(request: JobCreateRequest):
    return create_job(request)