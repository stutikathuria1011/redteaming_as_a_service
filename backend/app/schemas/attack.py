from typing import Optional

from pydantic import BaseModel


class GeneratedAttack(BaseModel):
    attack_id: str
    category: str
    prompt: str
    # Mutation family from the attack library ("original" = unmodified seed = baseline).
    family: Optional[str] = None
    system_context: Optional[str] = None


class AttackGenerationRequest(BaseModel):
    job_id: str
    model_name: str | None = None
    attack_categories: list[str]
    number_of_attacks: int


class AttackGenerationResponse(BaseModel):
    job_id: str
    attacks: list[GeneratedAttack]