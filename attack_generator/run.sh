#!/usr/bin/env bash
# macOS/Linux one-command setup + seed build.   Usage: bash run.sh [build_seed_dataset.py args]
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
python build_seed_dataset.py "$@"
echo
echo "Seeds built. Next (activate the venv first: source .venv/bin/activate):"
echo "  python generate_attacks.py --dry-run                    # see the plan and LLM-call count"
echo "  export ANTHROPIC_API_KEY=...   (or OPENAI_API_KEY)"
echo "  python generate_attacks.py --variants-per-seed 6"
