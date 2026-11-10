"""Run a second judge model on a pairs file, with and without system context. Writes separate files."""
import json, os, sys, time

from judge import judge

src = sys.argv[1]
tag = sys.argv[2]
limit = int(os.environ.get("LIMIT", "0")) or None
pairs = json.load(open(src))[:limit]

for name, use_ctx in (("", True), ("_nocontext", False)):
    path = src.replace(".json", f".judge_{tag}{name}.json")
    cache = json.load(open(path)) if os.path.exists(path) else {}
    for p in pairs:
        if p["id"] in cache:
            continue
        ctx = p.get("system_context") if use_ctx else None
        r = judge(p["attack_prompt"], p["target_response"], findings=False, context=ctx)
        cache[p["id"]] = r["severity_score"]
        json.dump(cache, open(path, "w"))
        print(f"{tag}{name} {p['id']}: {r['severity_score']}")
        time.sleep(0.3)
    print("wrote", path)
