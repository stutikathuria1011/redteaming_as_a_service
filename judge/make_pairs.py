"""Send attacks to a target model on an OpenAI-compatible API and save (attack, response) pairs.

Usage: python3 make_pairs.py attacks.json out.json --model <id> [--limit N] [--pause S]
                             [--base-url URL] [--key-env ENV_VAR_NAME]
Defaults target OpenRouter (OPENROUTER_API_KEY). Resumes if out.json exists.
Output pairs have no labels; label them with panel.py.
"""
import argparse
import json
import os
import time

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


def ask(client, model, prompt, max_tokens, system=None, retries=5):
    """Return the target's reply text, or None after repeated failures or an empty reply."""
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    for i in range(retries):
        try:
            r = client.chat.completions.create(
                model=model, messages=msgs, max_tokens=max_tokens
            )
            return (r.choices[0].message.content or "").strip() or None
        except Exception as e:
            print(f"  retry {i + 1}: {str(e)[:100]}")
            time.sleep(10 * (i + 1))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("attacks")
    ap.add_argument("out")
    ap.add_argument("--model", required=True)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--pause", type=float, default=5.0)
    ap.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    ap.add_argument("--key-env", default="OPENROUTER_API_KEY")
    a = ap.parse_args()

    attacks = json.load(open(a.attacks))[: a.limit]
    done = json.load(open(a.out)) if os.path.exists(a.out) else []
    seen = {p["id"] for p in done}
    client = OpenAI(base_url=a.base_url, api_key=os.environ[a.key_env])

    failed = 0
    for n, atk in enumerate(attacks, 1):
        aid = atk.get("attack_id") or atk.get("id")
        if aid in seen:
            continue
        prompt = atk.get("prompt") or atk["attack_prompt"]
        reply = ask(client, a.model, prompt, a.max_tokens, atk.get("system_context"))
        if reply is None:
            failed += 1
            print(f"{n}/{len(attacks)} {aid}: no reply")
            continue
        done.append({
            "id": aid,
            "category": atk.get("category"),
            "system_context": atk.get("system_context"),
            "attack_prompt": prompt,
            "target_response": reply,
            "target_model": a.model,
        })
        json.dump(done, open(a.out, "w"), indent=2)
        print(f"{n}/{len(attacks)} {aid}: {len(reply)} chars")
        time.sleep(a.pause)
    print(f"saved {len(done)} pairs to {a.out}, {failed} failed")


if __name__ == "__main__":
    main()