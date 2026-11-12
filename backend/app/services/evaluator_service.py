"""Adapter between the backend and the judge (judge/integration.py on main).

The judge folder is not a Python package: its files import each other by flat name
(`from analysis import ...`) and it has a module called judge.py. So the judge folder is
put on sys.path and `integration` / `report_pdf` are imported from there. That import
must happen AFTER the path is set, so it is done lazily inside functions.
"""
import asyncio
import os
import sys
from pathlib import Path

from app.schemas.evaluation import AttackResult, EvaluationResult

# .../<project root>/backend/app/services/evaluator_service.py -> parents[3] = project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]

_loaded = False


def find_judge_dir() -> Path:
    """Folder that contains integration.py. Set JUDGE_DIR in .env to force a location."""
    env = os.getenv("JUDGE_DIR")
    if env:
        path = Path(env).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if (path / "integration.py").exists():
            return path.resolve()
        raise RuntimeError(f"JUDGE_DIR={env} does not contain integration.py")

    patterns = [
        "judge-scoring/judge/integration.py",
        "judge/integration.py",
        "judge/judge/integration.py",
        "judge-scoring/integration.py",
    ]
    for pattern in patterns:
        for hit in sorted(PROJECT_ROOT.glob(pattern)):
            if (hit.parent / "judge.py").exists():
                return hit.parent.resolve()

    raise RuntimeError(
        f"Judge not found under {PROJECT_ROOT}. Put it at <project>/judge-scoring/judge "
        "or set JUDGE_DIR to the folder that contains integration.py."
    )


def _load_judge_modules() -> None:
    global _loaded
    if not _loaded:
        judge_dir = str(find_judge_dir())
        if judge_dir not in sys.path:
            # append, not insert(0): the judge's flat names (report, llm, ...) must not
            # shadow anything the backend already uses
            sys.path.append(judge_dir)
        _loaded = True


def judge_ready() -> tuple[bool, str]:
    """Pre-flight check. Without it, a missing GROQ_API_KEY makes the judge raise in the
    middle of a run, after every attack has already been sent to the target."""
    try:
        find_judge_dir()
    except RuntimeError as e:
        return False, str(e)

    provider = os.getenv("JUDGE_PROVIDER", "groq")
    key_env = {
        "groq": "GROQ_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": os.getenv("JUDGE_KEY_ENV", "OPENAI_API_KEY"),
    }.get(provider)

    if key_env is None:
        return False, f"Unknown JUDGE_PROVIDER '{provider}'"
    if not os.getenv(key_env):
        return False, f"{key_env} is not set (JUDGE_PROVIDER={provider})"
    return True, "ok"


async def evaluate_run(
    attack_results: list[AttackResult],
    on_progress=None,
) -> tuple[list[EvaluationResult], dict]:
    """Judge the whole run with ONE run_judge call and return (evaluations, report).

    run_judge judges every pair and builds the report in the same pass, so each pair
    reaches the judge API exactly once. Do not also call a per-attack evaluate.
    """
    _load_judge_modules()
    from integration import run_judge  # noqa: E402

    pause = float(os.getenv("JUDGE_PAUSE", "0.5"))

    out = await asyncio.to_thread(
        run_judge,
        [r.model_dump() for r in attack_results],
        pause=pause,
        on_progress=on_progress,
    )

    evaluations = [EvaluationResult(**e) for e in out["evaluations"]]
    return evaluations, out["report"]


async def generate_pdf_report(
    report: dict,
    job_id: str,
    target_name: str | None,
) -> str:
    """Render the PDF for a finished job and return its path."""
    _load_judge_modules()
    from report_pdf import render_pdf  # noqa: E402

    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    pdf_path = reports_dir / f"{job_id}.pdf"

    await asyncio.to_thread(render_pdf, report, str(pdf_path), target_name)

    return str(pdf_path)