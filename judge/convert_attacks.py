"""Convert Stuti's attacks.jsonl to the JSON list make_pairs.py reads, with filters.

Usage: python3 convert_attacks.py in.jsonl out.json [--family original] [--keep-bias] [--keep-benign]
"""
import argparse
import collections
import json

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("--family", default="original")
ap.add_argument("--keep-bias", action="store_true")
ap.add_argument("--keep-benign", action="store_true")
a = ap.parse_args()

rows = [json.loads(l) for l in open(a.src) if l.strip()]
keep = []
for r in rows:
    if a.family != "all" and r["family"] != a.family:
        continue
    if r["is_benign_control"] and not a.keep_benign:
        continue
    if r["category"] == "bias_elicitation" and not a.keep_bias:
        continue
    keep.append({k: r.get(k) for k in (
        "attack_id", "seed_id", "family", "category", "subcategory",
        "prompt", "system_context", "success_pattern", "expected_safe_behavior",
    )})

json.dump(keep, open(a.out, "w"), indent=2)
print(len(keep), "attacks written to", a.out)
print(collections.Counter((r["category"], bool(r["system_context"])) for r in keep))
