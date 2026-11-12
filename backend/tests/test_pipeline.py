"""End-to-end checks for the backend <-> judge <-> attack-library integration.

The target LLM and the judge's LLM calls are faked (no network, no quota). Everything
else is real: the attack file, run_judge, the report builder, the PDF renderer.
Run from the backend folder:  python -m pytest tests -q
"""
import collections
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("JUDGE_PAUSE", "0")
    monkeypatch.delenv("JUDGE_PROVIDER", raising=False)

    from app.services import evaluator_service as ev
    ev._load_judge_modules()
    import integration
    from report import build_report
    from judge import VERDICTS

    calls = []  # one entry per pair that reached the judge

    def fake_judge(attack, response, context=None, **kw):
        calls.append({"response": response, "context": context})
        if response.startswith("ERR"):
            return {"severity_score": None, "verdict": "error", "reason": "rate limit reached",
                    "category_confirmed": None, "finding": None, "recommendation": None}
        score = 3 if response.startswith("LEAK") else 0
        return {"severity_score": score, "verdict": VERDICTS[score], "reason": "r",
                "category_confirmed": True, "finding": "leak" if score else "none",
                "recommendation": "fix" if score else ""}

    monkeypatch.setattr(integration, "judge", fake_judge)
    monkeypatch.setattr(integration, "make_report", lambda rows: build_report(rows))
    return calls


def make_target(monkeypatch, reply):
    sent = []

    async def fake_send(target_url, api_key, model_name, prompt, system_context=None):
        sent.append({"prompt": prompt, "system": system_context})
        out = reply(prompt, system_context)
        if isinstance(out, Exception):
            raise out
        return out

    from app.services import run_service
    monkeypatch.setattr(run_service, "send_attack", fake_send)
    return sent


@pytest.fixture()
def client():
    from app.main import app
    return TestClient(app)


def body(n=12, cats=("jailbreak", "prompt_injection", "data_leakage"), **extra):
    return {"target_type": "api", "target_url": "http://target.invalid/v1/chat/completions",
            "model_name": "fake", "api_key": "k", "number_of_attacks": n,
            "attack_categories": list(cats), **extra}


def run(client, **kw):
    r = client.post("/jobs", json=body(**kw))
    assert r.status_code == 200, r.text
    return client.get(f"/jobs/{r.json()['job_id']}").json()


def test_init_files_are_double_underscore():
    bad = [p for p in (BACKEND / "app").rglob("_init_.py")]
    assert not bad, bad
    for d in [BACKEND / "app", *(p.parent for p in (BACKEND / "app").rglob("__init__.py"))]:
        assert (d / "__init__.py").exists()


def test_generator_spreads_categories_and_skips_benign(env):
    from app.services.generator_service import select_attacks
    picked = select_attacks(["jailbreak", "prompt_injection", "data_leakage"], 30, "seed")
    assert collections.Counter(r["category"] for r in picked) == {
        "jailbreak": 10, "prompt_injection": 10, "data_leakage": 10}
    assert not any(r["is_benign_control"] for r in picked)
    assert len({r["family"] for r in picked}) > 3          # family coverage, not one family
    assert select_attacks(["jailbreak"], 5, "s") == select_attacks(["jailbreak"], 5, "s")
    everything = select_attacks(["jailbreak"], 5000, "s")
    assert not any(r["is_benign_control"] for r in everything)


def test_full_flow_judges_each_pair_once(env, client, monkeypatch):
    sent = make_target(monkeypatch, lambda p, s: "LEAK secret" if "ignore" in p.lower() else "I cannot help")
    job = run(client, n=12)
    assert job["status"] == "completed", job["error"]
    assert len(sent) == 12 and len(env) == 12              # one target call and ONE judge call per pair
    assert len(job["evaluations"]) == 12 and job["report"]["summary"]["total"] == 12
    assert job["attack_success_rate"] == job["report"]["summary"]["attack_success_rate"]
    assert set(job["family_breakdown"]) <= {a["family"] for a in job["attacks"]}
    # canary scenarios: same system prompt reached the target AND the judge
    scen = [s for s in sent if s["system"]]
    assert scen and {c["context"] for c in env if c["context"]} == {s["system"] for s in scen}


def test_user_system_prompt_overrides_builtin_scenarios(env, client, monkeypatch):
    sent = make_target(monkeypatch, lambda p, s: "ok")
    job = run(client, n=9, cats=("prompt_injection", "data_leakage"), system_prompt="You are MyBot.")
    assert job["status"] == "completed"
    assert {s["system"] for s in sent} == {"You are MyBot."}
    assert {c["context"] for c in env} == {"You are MyBot."}
    assert all(r["system_context"] == "You are MyBot." for r in job["results"])


def test_unscored_is_never_safe_or_counted(env, client, monkeypatch):
    make_target(monkeypatch, lambda p, s: "ERRx" if len(p) % 2 else "LEAK y")
    job = run(client, n=10, cats=("jailbreak",))
    unscored = [e for e in job["evaluations"] if e["score"] is None]
    assert unscored, "test needs some unscored pairs"
    assert all(e["severity"] == "UNSCORED" and e["successful"] is False and e["error"] for e in unscored)
    s = job["report"]["summary"]
    assert s["errors"] == len(unscored) and s["scored"] == 10 - len(unscored)
    assert any("could not be scored" in w for w in job["warnings"])


def test_nothing_scored_gives_no_rate(env, client, monkeypatch):
    make_target(monkeypatch, lambda p, s: "ERR all")
    job = run(client, n=4, cats=("jailbreak",))
    assert job["status"] == "completed"
    assert job["report"]["summary"]["scored"] == 0
    assert job["attack_success_rate"] is None              # not 0%
    assert any("No pair could be scored" in w for w in job["warnings"])


def test_target_failures_skip_judge_and_total_failure_fails_job(env, client, monkeypatch):
    n = {"i": 0}
    def flaky(p, s):
        n["i"] += 1
        return RuntimeError("HTTP 500") if n["i"] % 3 == 0 else "fine"
    make_target(monkeypatch, flaky)
    job = run(client, n=9, cats=("jailbreak",))
    assert len(job["execution_errors"]) == 3 and len(job["results"]) == 6
    assert len(env) == 6                                   # failed attacks never reached the judge
    make_target(monkeypatch, lambda p, s: RuntimeError("down"))
    job = run(client, n=3, cats=("jailbreak",))
    assert job["status"] == "failed" and "down" in job["error"]


def test_preflight_and_validation(env, client, monkeypatch):
    r = client.post("/jobs", json=body(cats=("nope",)))
    assert r.status_code == 422
    assert client.post("/jobs", json={**body(), "target_url": None}).status_code == 422
    monkeypatch.delenv("GROQ_API_KEY")
    r = client.post("/jobs", json=body())
    assert r.status_code == 503 and "GROQ_API_KEY" in r.json()["detail"]
    assert client.get("/health").json()["judge_ready"] is False


def test_report_and_pdf_endpoints(env, client, monkeypatch):
    make_target(monkeypatch, lambda p, s: "LEAK z")
    job = run(client, n=6, cats=("jailbreak",))
    assert client.get(f"/jobs/{job['job_id']}/report").json()["report"]["summary"]["total"] == 6
    pdf = client.get(f"/jobs/{job['job_id']}/report.pdf")
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
    assert client.get("/jobs/does-not-exist/report").status_code == 404