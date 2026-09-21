from pydantic import BaseModel


class GeneratedAttack(BaseModel):
    attack_id: str
    category: str
    prompt: str


class AttackGenerationRequest(BaseModel):
    job_id: str
    model_name: str
    attack_categories: list[str]
    number_of_attacks: int


class AttackGenerationResponse(BaseModel):
    job_id: str
    attacks: list[GeneratedAttack]