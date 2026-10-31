import json
import time

from integration import run_judge
from report_pdf import render_pdf

examples = json.load(open("test_data/labeled_examples.json"))[::3]
runs = [
    {"attack_id": e["id"], "category": e["category"], "prompt": e["attack_prompt"], "target_response": e["target_response"]}
    for e in examples
]
start = time.time()
out = run_judge(runs, on_progress=lambda d, t: print(f"\r{d}/{t}", end="", flush=True))
print(f"\n{len(runs)} pairs in {time.time() - start:.0f}s")
ev = out["evaluations"]
print("unscored:", sum(e["score"] is None for e in ev), "| successful:", sum(e["successful"] for e in ev))
print("report keys:", list(out["report"]))
json.dump(out, open("test_data/e2e_out.json", "w"), indent=2, ensure_ascii=False)
render_pdf(out["report"], "test_data/e2e_report.pdf", target_name="Test target")
print("wrote test_data/e2e_out.json and test_data/e2e_report.pdf")
