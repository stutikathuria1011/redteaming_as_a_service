import json
import os
import random
from collections import Counter, defaultdict
from functools import lru_cache
from itertools import cycle
from pathlib import Path

from app.schemas.attack import (
    AttackGenerationRequest,
    AttackGenerationResponse,
    GeneratedAttack,
)


def get_attack_file() -> Path:
    env = os.getenv("ATTACKS_FILE")

    if env:
        attack_file = Path(env).expanduser()
    else:
        project_root = Path(__file__).resolve().parents[3]
        attack_file = (
            project_root
            / "attack_generator"
            / "out"
            / "attacks.jsonl"
        )

    if not attack_file.exists():
        raise FileNotFoundError(
            f"Attack dataset not found: {attack_file}"
        )

    return attack_file


@lru_cache(maxsize=1)
def _load_library(path: str) -> tuple[dict, ...]:
    rows = []

    with open(path, "r", encoding="utf-8") as file:

        for line_number, line in enumerate(file, start=1):

            if not line.strip():
                continue

            try:
                rows.append(json.loads(line))

            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON at line {line_number}"
                ) from exc

    # The judge scores harm only. Benign over-refusal controls (judge_mode
    # "over_refusal") would always come back "safe", so they are left out.
    return tuple(
        r for r in rows
        if not r.get("is_benign_control")
        and r.get("judge_mode", "harm") == "harm"
    )


def available_categories() -> dict[str, int]:
    """Category id -> number of usable attacks."""
    library = _load_library(str(get_attack_file()))
    return dict(Counter(r["category"].lower() for r in library))


def _interleave_by_family(pool: list[dict], rng: random.Random) -> list[dict]:
    """Shuffle, then rotate through the mutation families, so even a small run covers
    every family (including 'original', the unmodified baseline)."""
    by_family = defaultdict(list)

    for row in pool:
        by_family[row.get("family", "unknown")].append(row)

    families = sorted(by_family)
    rng.shuffle(families)

    for rows in by_family.values():
        rng.shuffle(rows)

    ordered = []

    for family in cycle(families):
        if not any(by_family.values()):
            break
        if by_family[family]:
            ordered.append(by_family[family].pop())

    return ordered


def select_attacks(
    categories: list[str],
    count: int,
    seed: str,
) -> list[dict]:
    """Pick `count` attacks spread evenly over the categories (round-robin).
    Same seed -> same selection. Returns fewer only if the library runs out."""
    rng = random.Random(seed)
    library = _load_library(str(get_attack_file()))

    wanted = [c.strip().lower() for c in categories]

    pools = {
        c: _interleave_by_family(
            [r for r in library if r["category"].lower() == c], rng
        )
        for c in wanted
    }

    picked = []

    while len(picked) < count and any(pools.values()):
        for c in wanted:
            if pools[c] and len(picked) < count:
                picked.append(pools[c].pop(0))

    return picked


async def generate_attacks(
    request: AttackGenerationRequest,
) -> AttackGenerationResponse:

    if request.number_of_attacks <= 0:
        raise ValueError(
            "Number of attacks must be greater than zero."
        )

    selected = select_attacks(
        request.attack_categories,
        request.number_of_attacks,
        seed=request.job_id,
    )

    if not selected:
        raise ValueError(
            "No attacks found for the requested categories."
        )

    attacks = [
        GeneratedAttack(
            attack_id=f"{request.job_id}-{attack['attack_id']}",
            category=attack["category"],
            prompt=attack["prompt"],
            family=attack.get("family"),
            system_context=attack.get("system_context"),
        )
        for attack in selected
    ]

    return AttackGenerationResponse(
        job_id=request.job_id,
        attacks=attacks,
    )