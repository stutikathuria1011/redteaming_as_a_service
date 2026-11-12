from typing import Optional

from pydantic import BaseModel


class AttackResult(BaseModel):
    attack_id: str
    category: str
    prompt: str
    target_response: str
    system_context: Optional[str] = None


class EvaluationResult(BaseModel):
    attack_id: str
    score: Optional[float] = None
    severity: str
    successful: bool
    finding: str
    reason: str
    error: Optional[str] = None