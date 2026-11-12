from fastapi import APIRouter

from app.services.evaluator_service import judge_ready

router = APIRouter()


@router.get("/health")
def health_check():
    ready, detail = judge_ready()

    return {
        "status": "ok",
        "service": "red-teaming-backend",
        "judge_ready": ready,
        "judge_detail": detail,
    }