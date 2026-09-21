from app.schemas.attack import (
    AttackGenerationRequest,
    AttackGenerationResponse,
    GeneratedAttack,
)


async def generate_attacks(
    request: AttackGenerationRequest,
) -> AttackGenerationResponse:

    attacks = []

    for i in range(request.number_of_attacks):
        category = request.attack_categories[
            i % len(request.attack_categories)
        ]

        attacks.append(
            GeneratedAttack(
                attack_id=f"{request.job_id}-attack-{i + 1}",
                category=category,
                prompt=f"Test attack {i + 1} for category: {category}",
            )
        )

    return AttackGenerationResponse(
        job_id=request.job_id,
        attacks=attacks,
    )