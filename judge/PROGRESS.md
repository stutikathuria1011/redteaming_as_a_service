# Judge progress log

Superseded. The earlier session log (13/15 accuracy on a 15-item set) is in git history and no longer reflects the judge.

Current state and results: see `judge/README.md` and the paper. Key points as of Nov 10, 2026:

- Judge: `openai/gpt-oss-120b` on Groq (free tier), scores-only mode for validation, provider switchable in `llm.py`.
- Development set (52 items, mostly synthetic, tuned on): 0.79 exact, 0.90 safe vs harmful.
- Real target responses (52 pairs, weak target with a system prompt holding planted canaries): the judge shown the system prompt flagged 17 of 21 harmful responses against 8 of 21 without it, 2 false flags of 31 against 0. Labels are LLM silver labels plus 11 author-adjudicated rows; see the paper for caveats.
