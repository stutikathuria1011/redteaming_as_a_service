#!/usr/bin/env python3
"""
RTaaS attack generator: expands out/seeds.jsonl into attack variants.

    python generate_attacks.py --provider anthropic --variants-per-seed 6      # needs ANTHROPIC_API_KEY
    python generate_attacks.py --provider openai --model gpt-4o-mini           # OPENAI_API_KEY (+OPENAI_BASE_URL)
    python generate_attacks.py --provider none                                  # no API: template families only
    python generate_attacks.py --dry-run                                        # show the plan + LLM-call count

Output: out/attacks.jsonl (one attack per line, ready for the target runner and the judge) + out/attacks_summary.txt
"""
import argparse, asyncio, json, random, re, sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from attackgen import prompts as P
from attackgen.llm import LLMError, make_client
from attackgen.mutators import ALL_FAMILIES, LLM_FAMILIES, mutate, salt

KEEP = ["category", "subcategory", "owasp", "system_context", "success_pattern", "expected_safe_behavior", "judge_mode",
        "detection_mode", "is_benign_control", "unbiased_option_letter", "unbiased_option_text", "source"]


def tokens(t): return set(re.findall(r"\w+", t.lower()))
def jaccard(a, b): return len(a & b) / max(1, len(a | b))


def load_tax():
    return yaml.safe_load(open(Path(__file__).with_name("taxonomy.yaml"), encoding="utf-8"))

def specs_for(seed, tax, requested):
    allowed = tax["benign_control_families"] if seed["is_benign_control"] else tax["categories"][seed["category"]]["families"]
    pool = requested if requested else allowed
    return [sp for sp in pool if all(step in allowed for step in sp.split(">"))]

def plan(seeds, tax, requested, per_seed):
    tasks = []
    for sd in seeds:
        specs = specs_for(sd, tax, requested)
        if not specs: continue
        off = salt(sd["id"]) % len(specs)
        for j in range(per_seed):
            tasks.append({"seed": sd, "spec": specs[(j + off) % len(specs)], "k": j // len(specs)})
    return tasks

def uses_llm(spec): return any(s in LLM_FAMILIES for s in spec.split(">"))


def record(seed, spec, k, prompt, method, model, parent_prompt):
    r = {"attack_id": None, "seed_id": seed["id"], "family": spec, "variant_index": k, "method": method,
         "generator_model": model if "llm" in method else None, "prompt": prompt,
         "diversity": round(1 - jaccard(tokens(parent_prompt), tokens(prompt)), 3)}
    r.update({key: seed.get(key) for key in KEEP})
    return r


async def run(args):
    rng = random.Random(args.seed)
    tax = load_tax()
    seeds = [json.loads(l) for l in open(args.seeds, encoding="utf-8") if l.strip()]
    requested = [f.strip() for f in args.families.split(",")] if args.families else None
    if requested:
        bad = [s for sp in requested for s in sp.split(">") if s not in ALL_FAMILIES]
        if bad: sys.exit(f"unknown families: {bad}. Valid: {sorted(ALL_FAMILIES)}")
    languages = [l.strip() for l in args.languages.split(",")]
    if any(l not in P.LANGUAGES for l in languages): sys.exit(f"languages must be from {list(P.LANGUAGES)}")

    tasks = plan(seeds, tax, requested, args.variants_per_seed)
    n_llm = sum(uses_llm(t["spec"]) for t in tasks) if args.provider not in ("none",) else 0
    print(f"{len(seeds)} seeds -> {len(tasks)} planned variants ({n_llm} need an LLM call; cached calls are free).")
    if args.dry_run: return
    if n_llm > args.max_llm_calls: sys.exit(f"Plan needs {n_llm} LLM calls > --max-llm-calls {args.max_llm_calls}. Raise it or reduce --variants-per-seed.")

    client = make_client(args.provider, args.model, cache_dir=None if args.no_cache else args.cache_dir,
                         temperature=args.temperature, concurrency=args.concurrency)
    model = client.model if client else None

    async def one(t):
        sd = t["seed"]
        try:
            return t, await mutate(t["spec"], sd.get("mutable_text", sd["text"]), sd, t["k"], client, languages)
        except LLMError as e:
            from attackgen.mutators import Result
            return t, Result(None, "llm", "api_error", str(e)[:200])

    results, done = [], 0
    for coro in asyncio.as_completed([one(t) for t in tasks]):
        results.append(await coro); done += 1
        if done % 100 == 0: print(f"  {done}/{len(tasks)}")

    by_seed = defaultdict(list)
    for t, r in results: by_seed[t["seed"]["id"]].append((t, r))
    out, status = [], Counter()
    for sd in seeds:
        orig = sd["text"]
        seen = {re.sub(r"\s+", " ", orig.lower())}
        if not args.no_originals: out.append(record(sd, "original", 0, orig, "none", None, orig))
        for t, r in sorted(by_seed[sd["id"]], key=lambda x: (x[0]["spec"], x[0]["k"])):
            status[(t["spec"], r.status)] += 1
            if r.text is None: continue
            prompt = sd.get("wrapper", "{m}").replace("{m}", r.text)
            key = re.sub(r"\s+", " ", prompt.lower())
            if key in seen: status[(t["spec"], "duplicate")] += 1; continue
            seen.add(key)
            out.append(record(sd, t["spec"], t["k"], prompt, r.method, model, orig))
    for i, a in enumerate(out, 1): a["attack_id"] = f"atk-{i:05d}"

    out_path = Path(args.out); out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for a in out: f.write(json.dumps(a, ensure_ascii=False) + "\n")

    gen = [a for a in out if a["family"] != "original"]
    L = [f"Attacks written: {len(out)} ({len(gen)} generated + {len(out) - len(gen)} originals) -> {out_path}",
         f"Provider: {args.provider}  model: {model}  API calls: {getattr(client, 'api_calls', 0)}  cache hits: {getattr(client, 'cache_hits', 0)}", "",
         "By category:"] + [f"  {k}: {v}" for k, v in sorted(Counter(a["category"] for a in gen).items())]
    L += ["", "By family (ok / failed) and mean diversity (1 = nothing shared with the seed):"]
    for fam in sorted({k[0] for k in status}):
        ok = status[(fam, "ok")]; bad = {s: n for (f, s), n in status.items() if f == fam and s != "ok"}
        div = [a["diversity"] for a in gen if a["family"] == fam]
        L.append(f"  {fam:32s} ok={ok:<4d} failed={bad or '-'}  diversity={sum(div) / len(div):.2f}" if div else f"  {fam:32s} ok=0 failed={bad}")
    refused = sum(n for (f, s), n in status.items() if s == "generator_refused")
    L += ["", f"Generator-LLM refusals: {refused} (these fall back to templates for role_play/hypothetical, otherwise are dropped)."]
    Path(out_path.parent / "attacks_summary.txt").write_text("\n".join(L), encoding="utf-8"); print("\n".join(L))


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default="out/seeds.jsonl")
    ap.add_argument("--out", default="out/attacks.jsonl")
    ap.add_argument("--provider", choices=["anthropic", "openai", "mock", "none"], default="anthropic")
    ap.add_argument("--model", default=None, help="default: claude-haiku-5-5 (anthropic) / gpt-4o-mini (openai)")
    ap.add_argument("--variants-per-seed", type=int, default=6)
    ap.add_argument("--families", default=None, help="comma list; chains allowed, e.g. paraphrase,role_play>multilingual")
    ap.add_argument("--languages", default="hi,hinglish,es,fr")
    ap.add_argument("--temperature", type=float, default=0.9)
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--max-llm-calls", type=int, default=3000)
    ap.add_argument("--cache-dir", default=".attackgen_cache")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--no-originals", action="store_true", help="omit the unmodified seeds (you want them as the baseline)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    return ap

if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
