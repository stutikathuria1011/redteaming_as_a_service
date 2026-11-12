from enum import Enum

from pydantic import BaseModel, Field, model_validator

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

    # NEW. The target's own system prompt, if it is deployed with one. When given, it is
    # sent to the target for every attack and passed to the judge as system_context.
    # When omitted, attacks that ship with their own scenario use that instead.
    system_prompt: str | None = None

    number_of_attacks: int = Field(gt=0, le=1000)

    attack_categories: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _need_target_url(self):
        if not self.target_url:
            raise ValueError(
                "target_url is required (an OpenAI-compatible chat/completions endpoint)"
            )
        return self


class JobStatus(str, Enum):
    CREATED = "created"
    GENERATING = "generating"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


class JobProgress(BaseModel):
    """Progress inside the current stage (executing: target calls, evaluating: judged pairs)."""

    done: int = 0
    total: int = 0


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus

    target_name: str | None = None
    progress: JobProgress = Field(default_factory=JobProgress)

    attacks: list[GeneratedAttack] = Field(default_factory=list)
    results: list[AttackResult] = Field(default_factory=list)
    evaluations: list[EvaluationResult] = Field(default_factory=list)

    # Judge report JSON, stored exactly as run_judge returned it.
    report: dict | None = None
    # None unless report["summary"]["scored"] > 0. Show this, not the report's own rate:
    # a run where nothing was scored has no meaningful rate.
    attack_success_rate: float | None = None
    # Success rate per mutation family (compare each with "original" = the baseline).
    family_breakdown: dict | None = None

    # Attacks the target gave no usable answer to. They are NOT sent to the judge.
    execution_errors: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # Why a FAILED job failed.
    error: str | None = None