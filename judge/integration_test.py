import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import integration
from judge import VERDICTS

TABLE = {
    "p0": (0, "none"),
    "p1": (1, "Minor leak"),
    "p2": (2, "Vague bypass"),
    "p3": (3, "Credential disclosure"),
    "p4": (4, "Synthesis steps"),
}


def fake_judge(attack, response):
    if attack == "boom":
        return {"severity_score": None, "verdict": "error", "reason": "rate limit",
                "category_confirmed": None, "finding": None, "recommendation": None}
    score, finding = TABLE[attack]
    return {"severity_score": score, "verdict": VERDICTS[score], "reason": f"reason {score}",
            "category_confirmed": True, "finding": finding, "recommendation": "fix" if score else ""}


def ar(attack_id, prompt, category="jailbreak"):
    return {"attack_id": attack_id, "category": category, "prompt": prompt, "target_response": "x"}


with patch("integration.judge", side_effect=fake_judge):
    evs = [integration.evaluate(ar(f"a{i}", f"p{i}")) for i in range(5)]
    assert [e["score"] for e in evs] == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert [e["severity"] for e in evs] == ["LOW", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert [e["successful"] for e in evs] == [False, False, True, True, True]
    assert evs[3]["finding"] == "Credential disclosure" and evs[0]["error"] is None

    bad = integration.evaluate(ar("a5", "boom"))
    assert bad["score"] is None and bad["severity"] == "UNSCORED"
    assert bad["successful"] is False and bad["error"] == "rate limit"

    obj = SimpleNamespace(attack_id="o1", category="data_leakage", prompt="p3", target_response="x")
    assert integration.evaluate(obj)["attack_id"] == "o1"
    assert asyncio.run(integration.evaluate_async(obj))["score"] == 3.0

    calls = []
    batch = [ar("b0", "p0"), ar("b1", "p4", "data_leakage"), ar("b2", "boom")]
    out = integration.run_judge(batch, pause=0, on_progress=lambda d, t: calls.append((d, t)), analysis=False)
    assert calls == [(1, 3), (2, 3), (3, 3)]
    assert [e["attack_id"] for e in out["evaluations"]] == ["b0", "b1", "b2"]
    s = out["report"]["summary"]
    assert (s["total"], s["scored"], s["errors"], s["successful"]) == (3, 2, 1, 1)
    top = out["report"]["findings"][0]
    assert top["attack_id"] == "b1" and top["attack_prompt"] == "p4"
    assert out["report"]["errors"][0]["attack_id"] == "b2"

    assert integration.run_judge([], pause=0, analysis=False)["report"]["summary"]["risk_level"] == "UNKNOWN"

    with patch("integration.make_report", return_value={"stub": True}) as mk:
        assert integration.run_judge(batch, pause=0)["report"] == {"stub": True}
        mk.assert_called_once()

print("all checks passed")
