"""Run:  python -m pytest functions/tests -q   (or: python functions/tests/test_empathy.py)"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import empathy as E

WARM = ("I'm so sorry — that sounds incredibly painful, and it makes sense that you feel numb. Grief doesn't follow a script, "
        "and you're not alone in this. What has these two weeks been like for you?")
COLD = "You should make a plan. Here are steps: 1. Update your resume. 2. Apply to jobs. 3. Don't worry, it could be worse."

def fake_post(url, headers, payload, timeout):
    """Minimal fake of an OpenAI-compatible and an Anthropic endpoint; the 'judge' call is recognised by its prompt."""
    msgs = payload["messages"]; user = msgs[-1]["content"]
    model = payload["model"]
    if "Rate the reply on four dimensions" in user:
        good = "I'm so sorry" in user
        txt = json.dumps({"emotional_reaction": 5 if good else 1, "interpretation": 4 if good else 2, "exploration": 4 if good else 1, "appropriateness": 5 if good else 2, "rationale": "stub"})
    elif model == "broken/model":
        return {"choices": []}
    else:
        txt = WARM if model.startswith("warm") else COLD
    if "anthropic.com" in url:
        return {"content": [{"type": "text", "text": txt}]}
    return {"choices": [{"message": {"content": txt}}]}

def test_heuristic_orders_warm_above_cold():
    assert E.heuristic_score(WARM)["score"] > E.heuristic_score(COLD)["score"] + 25

def test_parse_judge():
    assert E.parse_judge('noise {"emotional_reaction":4,"interpretation":3,"exploration":2,"appropriateness":5,"rationale":"ok"} tail')["exploration"] == 2
    assert E.parse_judge('{"emotional_reaction":9,"interpretation":3,"exploration":2,"appropriateness":5}') is None
    assert E.parse_judge("no json") is None

def test_think_tags_removed():
    def p(*a, **k): return {"choices": [{"message": {"content": "<think>secret</think>hello there"}}]}
    assert E.chat("openai", "m", "k", "hi", post=p) == "hello there"

def test_run_benchmark_ranks_models_and_handles_errors():
    models = [{"provider": "hf", "model": "cold/model"}, {"provider": "hf", "model": "warm/model"},
              {"provider": "anthropic", "model": "warm-claude", "api_key": "sk-user"}, {"provider": "hf", "model": "broken/model"}]
    res = E.run_benchmark(models, None, 3, {"provider": "hf", "model": "judge/x"}, {"hf": "hf_server"}, post=fake_post)
    names = [m["model"] for m in res["models"]]
    assert names[0].startswith("warm") and "cold/model" in names
    broken = [m for m in res["models"] if m["model"] == "broken/model"][0]
    assert broken["summary"]["n_ok"] == 0 and broken["summary"]["errors"]
    warm = [m for m in res["models"] if m["model"] == "warm/model"][0]
    assert warm["summary"]["overall"] > 80 and warm["summary"]["judged"] == 3
    # no key leaks into the output
    assert "sk-user" not in json.dumps(res) and "hf_server" not in json.dumps(res)

def test_no_judge_falls_back_to_heuristic():
    res = E.run_benchmark([{"provider": "hf", "model": "warm/model"}], None, 2, None, {"hf": "t"}, post=fake_post)
    assert res["judge"] is None and res["models"][0]["summary"]["judged"] == 0 and res["models"][0]["summary"]["overall"] > 40

def test_limits_and_validation():
    import pytest
    with pytest.raises(ValueError): E.run_benchmark([], None, 2, None, {})
    with pytest.raises(ValueError): E.run_benchmark([{"provider": "evil", "model": "x/y"}], None, 2, None, {})
    with pytest.raises(ValueError): E.run_benchmark([{"provider": "hf", "model": "bad name; rm -rf"}], None, 2, None, {})
    with pytest.raises(ValueError): E.run_benchmark([{"provider": "hf", "model": f"m/{i}"} for i in range(9)], None, 2, None, {})
