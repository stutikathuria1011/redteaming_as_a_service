import json
import statistics
import sys
import os
import time
from judge import judge

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5

with open("test_data/labeled_examples.json") as f:
    examples = json.load(f)
skipped = [e["id"] for e in examples if e.get("contested")]
examples = [e for e in examples if not e.get("contested")]
print(f"{len(examples)} examples, excluding contested: {skipped}")

PAUSE = float(os.environ.get("STAB_SLEEP", 1))
errors = []
run_hits = run_total = vote_hits = coarse_hits = 0
for ex in examples:
    scores = []
    for _ in range(N):
        r = judge(ex["attack_prompt"], ex["target_response"], findings=not os.environ.get("SCORES_ONLY"))
        if r["severity_score"] is not None:
            scores.append(r["severity_score"])
        else:
            errors.append(r["reason"][:600])
        time.sleep(PAUSE)  # stay under the free-tier rate limit
    if not scores:
        print(f"{ex['id']}: all runs errored")
        continue
    med = statistics.median_low(scores)
    run_hits += sum(s == ex["correct_score"] for s in scores)
    coarse_hits += sum((s >= 2) == (ex["correct_score"] >= 2) for s in scores)
    run_total += len(scores)
    vote_hits += med == ex["correct_score"]
    print(f"{ex['id']} label={ex['correct_score']} scores={scores} median={med} {'✓' if med == ex['correct_score'] else '✗'}")

print(f"\nSingle-run accuracy: {run_hits}/{run_total} = {run_hits / run_total:.2f}")
print(f"Safe vs harmful accuracy: {coarse_hits}/{run_total} = {coarse_hits / run_total:.2f}")
print(f"Median-of-{N} accuracy: {vote_hits}/{len(examples)}")
for msg in sorted(set(errors)):
    print(f"ERR x{errors.count(msg)}: {msg}")
