from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.attack import GeneratedAttack
from app.schemas.evaluation import AttackResult, EvaluationResult


class TargetType(str, Enum):
    API = "api"
    MODEL = "model"


class JobCreateRequest(BaseModel):
    target_type: TargetType

    target_url: str | None = None
    model_name: str | None = None
    api_key: str | None = None

    number_of_attacks: int = Field(gt=0, le=1000)

    attack_categories: list[str] = Field(min_length=1)


class JobStatus(str, Enum):
    CREATED = "created"
    GENERATING = "generating"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus

    attacks: list[GeneratedAttack] = Field(default_factory=list)
    results: list[AttackResult] = Field(default_factory=list)
    evaluations: list[EvaluationResult] = Field(default_factory=list)