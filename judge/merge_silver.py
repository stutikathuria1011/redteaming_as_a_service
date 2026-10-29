import json
import statistics
from collections import Counter

POOL = "test_data/pool_001.json"
PANEL = "test_data/labels_panel.json"
DEST = "test_data/labeled_examples.json"
VERDICTS = ["safe", "partial_resistance", "soft_compliance", "compliance", "full_compliance"]

pool = json.load(open(POOL))
panel = json.load(open(PANEL))
dest = json.load(open(DEST))
have = {e["id"] for e in dest}

added = skipped = 0
for ex in pool:
    scores = {m: v["score"] for m, v in panel.get(ex["id"], {}).items()}
    if ex["id"] in have or len(scores) < 2:
        skipped += 1
        continue
    silver = statistics.median_low(list(scores.values()))
    dest.append({**ex, "correct_score": silver, "correct_verdict": VERDICTS[silver],
                 "source": "synthetic_pool_001", "labeler": "panel_silver",
                 "panel_scores": scores,
                 "contested": max(scores.values()) - min(scores.values()) >= 2})
    added += 1

json.dump(dest, open(DEST, "w"), indent=2, ensure_ascii=False)
print(f"added {added}, skipped {skipped}, total {len(dest)}")
print("by score:", sorted(Counter(e["correct_score"] for e in dest).items()))
print("contested:", sorted(e["id"] for e in dest if e.get("contested")))
