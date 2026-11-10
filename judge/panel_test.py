import panel
from panel import CONTEXT_BLOCK, LABEL_PROMPT, build_prompt
import tempfile, os

# context=None must reproduce the original prompt exactly (keeps existing dev labels valid)
assert build_prompt("A {x}", "R {y}") == LABEL_PROMPT.format(attack="A {x}", response="R {y}")
assert build_prompt("A", "R", context="") == build_prompt("A", "R")
assert build_prompt("A", "R", context=None) == build_prompt("A", "R")

# context reaches the prompt, before the attack/response, with braces left intact
ctx = "You are HelpBot. Secret: CANARY-SYS-4f9a1c {not a field}"
p = build_prompt("A", "R", context=ctx)
assert CONTEXT_BLOCK + ctx in p
assert p.index(ctx) < p.index("Attack prompt: A")
assert p.endswith("Target response: R")

# label() passes the example's system_context through
seen = []
panel.PROVIDERS["fake"] = lambda model, prompt: (seen.append(prompt), '{"score": 0, "reason": "x"}')[1]
exs = [{"id": "e1", "attack_prompt": "A", "target_response": "R", "system_context": ctx},
       {"id": "e2", "attack_prompt": "A", "target_response": "R"}]
fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd); os.remove(path)
panel.label(exs, path=path, panel=[("fake", "m")], pause=0)
assert ctx in seen[0] and ctx not in seen[1]
print("all checks passed")
