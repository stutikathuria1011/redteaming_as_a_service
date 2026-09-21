from pydantic import BaseModel


class AttackResult(BaseModel):
    attack_id: str
    category: str
    prompt: str
    target_response: str


class EvaluationResult(BaseModel):
    attack_id: str
    score: float
    severity: str
    successful: bool
    finding: str
    reason: str