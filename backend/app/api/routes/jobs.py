from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from app.schemas.job import JobCreateRequest, JobResponse, JobStatus
from app.services.evaluator_service import generate_pdf_report, judge_ready
from app.services.generator_service import available_categories
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
    # Fail now, not after every attack has already been sent to the target.
    ready, detail = judge_ready()

    if not ready:
        raise HTTPException(
            status_code=503,
            detail=f"Judge is not ready: {detail}",
        )

    known = available_categories()
    unknown = sorted(
        {c.strip().lower() for c in request.attack_categories} - set(known)
    )

    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown attack categories {unknown}. Available: {sorted(known)}",
        )

    job = create_job(request)

    background_tasks.add_task(
        run_job,
        job_id=job.job_id,
        model_name=request.model_name,
        target_url=request.target_url,
        api_key=request.api_key,
        number_of_attacks=request.number_of_attacks,
        attack_categories=request.attack_categories,
        system_prompt=request.system_prompt,
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


def _completed_job(job_id: str) -> JobResponse:
    job = get_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED or job.report is None:
        raise HTTPException(
            status_code=409,
            detail=f"Report not available (job status: {job.status.value})",
        )

    return job


@router.get("/{job_id}/report")
def get_job_report(job_id: str):
    job = _completed_job(job_id)

    return {
        "job_id": job.job_id,
        "target_name": job.target_name,
        # None when nothing was scored: show "no result", never 0%.
        "attack_success_rate": job.attack_success_rate,
        "family_breakdown": job.family_breakdown,
        "warnings": job.warnings,
        "report": job.report,
    }


@router.get("/{job_id}/report.pdf")
async def get_job_report_pdf(job_id: str):
    job = _completed_job(job_id)

    path = await generate_pdf_report(
        job.report,
        job.job_id,
        job.target_name,
    )

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"red-team-report-{job.job_id[:8]}.pdf",
    )