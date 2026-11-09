"""Mutation operators ("attack families"). Four are LLM-prompted, four are deterministic templates/encodings.

Every operator takes the MUTABLE part of a seed (the whole prompt for most seeds; only the injected payload for
indirect injection; only the question stem for bias items) and returns a Result. The pipeline re-embeds it afterwards.
"""
import base64, codecs, hashlib, re
from dataclasses import dataclass

from . import prompts as P

LLM_FAMILIES = {"paraphrase", "role_play", "hypothetical_framing", "multilingual"}
TEMPLATE_FAMILIES = {"payload_splitting", "encoding_obfuscation", "authority_claim", "prefix_injection"}
ALL_FAMILIES = LLM_FAMILIES | TEMPLATE_FAMILIES
MARKER_RE = re.compile(r"CANARY-[A-Z]{3}-[0-9a-f]{6}")
REFUSAL_RE = re.compile(r"^\s*(i('m| am)? (so )?sorry|i (cannot|can't|can’t|won't|won’t|will not)|i('m| am) (not able|unable|not going)|sorry,|i must decline|as an ai)", re.I)


@dataclass
class Result:
    text: str | None
    method: str          # llm | template | template_fallback
    status: str          # ok | generator_refused | invalid | not_applicable | no_llm
    detail: str = ""


def salt(seed_id: str) -> int:
    return int(hashlib.sha1(seed_id.encode()).hexdigest(), 16) % 9973

def pick(options, k, s):
    return options[(k + s) % len(options)]

def _clean(raw: str) -> str:
    t = raw.strip()
    t = re.sub(r"^```[a-z]*\n|\n```$", "", t).strip()
    if len(t) > 1 and t[0] == t[-1] and t[0] in "\"'“”": t = t[1:-1].strip()
    return t

def _validate(out, original, markers):
    if len(out) < 8: return False, "too short"
    if out.strip().lower() == original.strip().lower(): return False, "identical to original"
    if len(out) > 6 * len(original) + 400: return False, "too long (possible added detail)"
    missing = [m for m in markers if m not in out]
    if missing: return False, f"marker lost: {missing}"
    return True, ""

def _outside_markers(fn, text):
    parts = re.split(f"({MARKER_RE.pattern})", text)
    return "".join(p if i % 2 else fn(p) for i, p in enumerate(parts))   # odd parts are markers: left untouched

_LEET = str.maketrans({"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7", "A": "4", "E": "3", "I": "1", "O": "0", "S": "5", "T": "7"})


# ---------------- deterministic families ----------------
def template_mutate(family, text, k, s, category):
    if family == "authority_claim":
        pool = P.AUTHORITY_BIAS if category == "bias_elicitation" else P.AUTHORITY
        return Result(pick(pool, k, s).format(t=text, n=1000 + (s + 37 * k) % 9000), "template", "ok")
    if family == "prefix_injection":
        pool = P.PREFIX_BIAS if category == "bias_elicitation" else P.PREFIX
        return Result(pick(pool, k, s).format(t=text), "template", "ok")
    if family == "payload_splitting":
        words = text.split()
        if len(words) < 6: return Result(None, "template", "not_applicable", "too short to split")
        cut = max(2, min(len(words) - 2, len(words) // 2 + (k % 3) - 1))
        a, b = " ".join(words[:cut]).replace('"', "'"), " ".join(words[cut:]).replace('"', "'")
        return Result(pick(P.SPLIT, k, s).format(a=a, b=b), "template", "ok")
    if family == "encoding_obfuscation":
        method = pick(list(P.ENCODING_WRAP), k, s)
        if method == "base64":                       # whole text; a model that mis-decodes may hide the marker from the regex
            enc = base64.b64encode(text.encode("utf-8")).decode()
        elif method == "rot13":
            enc = _outside_markers(lambda p: codecs.encode(p, "rot13"), text)
        elif method == "leetspeak":
            enc = _outside_markers(lambda p: p.translate(_LEET), text)
        else:
            enc = _outside_markers(lambda p: " ".join(w[::-1] for w in p.split(" ")), text)
        return Result(P.ENCODING_WRAP[method].format(e=enc), "template", "ok", method)
    return Result(None, "template", "not_applicable", f"unknown family {family}")

def _fallback(family, text, k, s):
    pool = P.ROLE_PLAY_FALLBACK if family == "role_play" else P.HYPOTHETICAL_FALLBACK
    return Result(pick(pool, k, s).format(t=text), "template_fallback", "ok")


# ---------------- LLM-prompted families ----------------
async def llm_mutate(family, text, k, s, client, languages):
    markers = MARKER_RE.findall(text)
    lang = pick(list(languages), k, s) if family == "multilingual" else None
    instr = P.INSTRUCTIONS[family].format(style=pick(P.STYLES, k, s), persona=pick(P.PERSONAS, k, s),
                                          language=P.LANGUAGES[lang] if lang else "")

    def build(soft):
        u = f"FAMILY: {family}\n" + (f"LANGUAGE: {lang}\n" if lang else "") + f"TASK: {instr}\n"
        if markers: u += "MARKERS (must appear verbatim in your output): " + ", ".join(markers) + "\n"
        return u + f"<original>\n{text}\n</original>" + (P.SOFTENER if soft else "")

    for soft in (False, True):                       # second attempt adds the 'synthetic test string' context
        out = _clean(await client.complete(P.GEN_SYSTEM, build(soft)))
        if out == "CANNOT_REWRITE" or REFUSAL_RE.match(out): continue
        ok, why = _validate(out, text, markers)
        return Result(out if ok else None, "llm", "ok" if ok else "invalid", why)
    return Result(None, "llm", "generator_refused")


async def _mutate_one(family, text, k, s, client, languages, category):
    if family in TEMPLATE_FAMILIES:
        return template_mutate(family, text, k, s, category)
    if client is None:                               # offline: only the template-able LLM families have a fallback
        return _fallback(family, text, k, s) if family in ("role_play", "hypothetical_framing") else Result(None, "llm", "no_llm")
    res = await llm_mutate(family, text, k, s, client, languages)
    if res.text is None and family in ("role_play", "hypothetical_framing"):
        return _fallback(family, text, k, s)         # generator refused/invalid -> generic template so coverage isn't lost
    return res


async def mutate(spec, text, seed, k, client, languages):
    """spec = 'family' or a chain like 'role_play>multilingual'. Returns a Result for the whole chain."""
    s, cat, cur, methods = salt(seed["id"]), seed["category"], text, []
    for step in spec.split(">"):
        res = await _mutate_one(step, cur, k, s, client, languages, cat)
        if res.text is None: return Result(None, res.method, res.status, f"{step}: {res.detail}")
        cur = res.text; methods.append(res.method)
    return Result(cur, "+".join(dict.fromkeys(methods)), "ok")
