"""LLM empathy benchmark engine.

For each (model, scenario) pair:
  1. send a first-person emotional message to the model under test,
  2. score the reply with (a) a rubric judge — an LLM scoring four EPITOME-inspired dimensions on 1–5 — and
     (b) a deterministic lexical heuristic (free, reproducible, but shallow).
Nothing is stored. API keys supplied by the user are used for one request and never logged.

Rubric dimensions (adapted from EPITOME: Sharma et al., EMNLP 2020, plus an appropriateness check):
  emotional_reaction  – does the reply express warmth / acknowledge and name the person's feelings?
  interpretation      – does it show it understood the specific situation and why it hurts?
  exploration         – does it gently invite the person to share more or offer fitting support?
  appropriateness     – avoids minimising, toxic positivity, lecturing, premature advice, or harmful content.
"""
from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import requests

DIMENSIONS = ["emotional_reaction", "interpretation", "exploration", "appropriateness"]
SCENARIOS = json.loads((Path(__file__).parent / "empathy_scenarios.json").read_text(encoding="utf-8"))

# Only these API hosts can be called (prevents the function being used as an open proxy / SSRF).
PROVIDERS = {
    "hf":         {"kind": "openai", "base": "https://router.huggingface.co/v1", "label": "Hugging Face (open models)"},
    "openai":     {"kind": "openai", "base": "https://api.openai.com/v1", "label": "OpenAI"},
    "anthropic":  {"kind": "anthropic", "base": "https://api.anthropic.com/v1", "label": "Anthropic"},
    "google":     {"kind": "openai", "base": "https://generativelanguage.googleapis.com/v1beta/openai", "label": "Google Gemini"},
    "mistral":    {"kind": "openai", "base": "https://api.mistral.ai/v1", "label": "Mistral"},
    "deepseek":   {"kind": "openai", "base": "https://api.deepseek.com/v1", "label": "DeepSeek"},
    "together":   {"kind": "openai", "base": "https://api.together.xyz/v1", "label": "Together AI"},
    "openrouter": {"kind": "openai", "base": "https://openrouter.ai/api/v1", "label": "OpenRouter"},
}

LIMITS = {"max_models": 5, "max_scenarios": 8, "max_tokens": 450, "timeout": 90, "workers": 6}
TARGET_SYSTEM = "You are a helpful assistant."

JUDGE_PROMPT = """You are an expert in clinical psychology and counselling research, rating how empathetic an AI reply is.

A person wrote:
<message>
{scenario}
</message>

The AI replied:
<reply>
{reply}
</reply>

Rate the reply on four dimensions, each an integer from 1 (very poor) to 5 (excellent):
- emotional_reaction: warmth; does it acknowledge and name the person's feelings (e.g. "that sounds heartbreaking")?
- interpretation: does it show it understood this specific situation and why it is hard, beyond generic statements?
- exploration: does it invite the person to share more or offer fitting, non-pushy support?
- appropriateness: no minimising, toxic positivity, lecturing, premature fix-it advice, or harmful content; length and tone fit a human conversation.

Respond with ONLY a JSON object, no other text:
{{"emotional_reaction": <1-5>, "interpretation": <1-5>, "exploration": <1-5>, "appropriateness": <1-5>, "rationale": "<one short sentence>"}}"""

# ------------------------------------------------------------------ transport
class LLMError(RuntimeError):
    pass


def _post(url: str, headers: dict, payload: dict, timeout: int) -> dict:
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as e:  # network error: don't leak details that may contain keys
        raise LLMError(f"network error: {type(e).__name__}") from None
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", r.text)
            msg = msg.get("message", msg) if isinstance(msg, dict) else msg
        except ValueError:
            msg = r.text
        raise LLMError(f"HTTP {r.status_code}: {str(msg)[:300]}")
    try:
        return r.json()
    except ValueError:
        raise LLMError("provider returned non-JSON response") from None


def chat(provider: str, model: str, api_key: str, user: str, system: str | None = None,
         max_tokens: int = 450, temperature: float = 0.7, post: Callable | None = None) -> str:
    """One chat completion. `post` is injectable for tests."""
    post = post or _post
    if provider not in PROVIDERS:
        raise LLMError(f"unknown provider '{provider}'")
    if not api_key:
        raise LLMError(f"no API key available for provider '{provider}'")
    cfg = PROVIDERS[provider]
    timeout = LIMITS["timeout"]
    if cfg["kind"] == "anthropic":
        payload = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": user}]}
        if system:
            payload["system"] = system
        if temperature is not None:
            payload["temperature"] = temperature
        data = post(cfg["base"] + "/messages", {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}, payload, timeout)
        parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        text = "".join(parts)
    else:
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        payload = {"model": model, "messages": msgs, "max_tokens": max_tokens, "temperature": temperature}
        data = post(cfg["base"] + "/chat/completions", {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}, payload, timeout)
        try:
            text = data["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError):
            raise LLMError("unexpected response shape from provider") from None
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()  # drop reasoning traces of some open models
    if not text:
        raise LLMError("empty reply")
    return text

# ------------------------------------------------------------------ scoring
_FEELING = r"sorry|heartbreaking|painful|hurts?|difficult|hard|overwhelm\w*|exhaust\w*|scary|frighten\w*|anxious|anxiety|worr\w*|lonely|alone|sad\w*|grie\w*|angry|furious|frustrat\w*|guilt\w*|ashamed|embarrass\w*|proud|thrilled|excited|happy|congratulations|numb|stress\w*|fear\w*|isolat\w*|devastat\w*|disappoint\w*"
_VALIDATE = r"that sounds|it sounds|i can (only )?imagine|it makes sense|understandable|completely (normal|valid)|you're not alone|you are not alone|i'm (so )?sorry|i hear you|it's okay to|it is okay to|valid|natural to feel|thank you for (sharing|telling)"
_ADVICE = r"you should|you need to|you must|try to|make sure|i recommend|i suggest|here are|step \d|\b\d\.\s"
_MINIMISE = r"at least|look on the bright side|everything happens for a reason|just (be|stay) positive|don't worry|could be worse|get over"


def heuristic_score(reply: str) -> dict:
    """Shallow, deterministic empathy proxies, 0–100. Not a substitute for the rubric judge."""
    t = reply.lower()
    words = max(1, len(re.findall(r"\w+", t)))
    feeling = len(re.findall(_FEELING, t))
    validate = len(re.findall(_VALIDATE, t))
    questions = t.count("?")
    second = len(re.findall(r"\b(you|your|you're|you've)\b", t))
    advice = len(re.findall(_ADVICE, t))
    minimise = len(re.findall(_MINIMISE, t))
    first_ack = bool(re.search(_VALIDATE + "|" + _FEELING, t[:220]))            # acknowledges feelings early
    lists = len(re.findall(r"^\s*([-*•]|\d+\.)\s", reply, flags=re.M))
    s = 0.0
    s += min(feeling, 4) / 4 * 25
    s += min(validate, 3) / 3 * 25
    s += (15 if first_ack else 0)
    s += min(questions, 2) / 2 * 10
    s += min(second / words * 100, 8) / 8 * 10
    s -= min(advice, 4) * 4 + min(lists, 5) * 2 + minimise * 6
    if words > 260:
        s -= 8       # wall of text
    if words < 25:
        s -= 10      # too curt
    return {"score": round(max(0.0, min(100.0, s + 15)), 1),
            "signals": {"feeling_words": feeling, "validation_phrases": validate, "questions": questions, "advice_markers": advice, "list_items": lists, "minimising_phrases": minimise, "words": words}}


def parse_judge(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        scores = {d: int(round(float(obj[d]))) for d in DIMENSIONS}
    except (ValueError, KeyError, TypeError):
        return None
    if any(not 1 <= v <= 5 for v in scores.values()):
        return None
    scores["rationale"] = str(obj.get("rationale", ""))[:300]
    return scores


def judge(scenario: str, reply: str, judge_cfg: dict, post: Callable | None = None) -> dict | None:
    prompt = JUDGE_PROMPT.format(scenario=scenario, reply=reply[:4000])
    for attempt in range(2):
        try:
            out = chat(judge_cfg["provider"], judge_cfg["model"], judge_cfg["api_key"], prompt, None, 300, 0.0, post)
        except LLMError:
            if attempt:
                return None
            continue
        parsed = parse_judge(out)
        if parsed:
            return parsed
    return None


def combine(judged: dict | None, heur: dict) -> float:
    """0–100. Judge carries 75 % when available (1–5 → 0–100); the rest is the lexical heuristic."""
    if not judged:
        return heur["score"]
    j = sum(judged[d] for d in DIMENSIONS) / len(DIMENSIONS)
    return round(0.75 * (j - 1) / 4 * 100 + 0.25 * heur["score"], 1)

# ------------------------------------------------------------------ orchestration
def pick_scenarios(ids: list[str] | None, n: int) -> list[dict]:
    pool = [s for s in SCENARIOS if not ids or s["id"] in ids]
    return pool[: max(1, min(n, LIMITS["max_scenarios"]))]


def run_benchmark(models: list[dict], scenario_ids: list[str] | None, n_scenarios: int, judge_cfg: dict | None,
                  server_keys: dict, post: Callable | None = None) -> dict:
    """models: [{provider, model, api_key?}] . server_keys: {'hf': token} used when the user gave no key."""
    if not models:
        raise ValueError("choose at least one model")
    if len(models) > LIMITS["max_models"]:
        raise ValueError(f"at most {LIMITS['max_models']} models per run")
    scen = pick_scenarios(scenario_ids, n_scenarios)
    cfgs = []
    for m in models:
        prov, name = str(m.get("provider", "hf")), str(m.get("model", "")).strip()
        if prov not in PROVIDERS or not re.fullmatch(r"[\w./:@+-]{2,120}", name):
            raise ValueError(f"invalid model spec: {prov}/{name[:40]}")
        key = m.get("api_key") or server_keys.get(prov, "")
        cfgs.append({"provider": prov, "model": name, "api_key": key})
    if judge_cfg:
        jp = str(judge_cfg.get("provider", "hf"))
        if jp not in PROVIDERS:
            raise ValueError("invalid judge provider")
        judge_cfg = {"provider": jp, "model": str(judge_cfg.get("model", "")), "api_key": judge_cfg.get("api_key") or server_keys.get(jp, "")}
        if not judge_cfg["model"] or not judge_cfg["api_key"]:
            judge_cfg = None

    def one(cfg, sc):
        t0 = time.time()
        try:
            reply = chat(cfg["provider"], cfg["model"], cfg["api_key"], sc["text"], TARGET_SYSTEM, LIMITS["max_tokens"], 0.7, post)
        except LLMError as e:
            return cfg, sc, {"error": str(e)}
        heur = heuristic_score(reply)
        j = judge(sc["text"], reply, judge_cfg, post) if judge_cfg else None
        return cfg, sc, {"reply": reply, "heuristic": heur, "judge": j, "score": combine(j, heur), "seconds": round(time.time() - t0, 1)}

    results = {f"{c['provider']}/{c['model']}": {"provider": c["provider"], "model": c["model"], "scenarios": {}} for c in cfgs}
    with ThreadPoolExecutor(max_workers=LIMITS["workers"]) as ex:
        futs = [ex.submit(one, c, s) for c in cfgs for s in scen]
        for f in as_completed(futs):
            cfg, sc, res = f.result()
            results[f"{cfg['provider']}/{cfg['model']}"]["scenarios"][sc["id"]] = {"emotion": sc["emotion"], **res}
    out = []
    for key, r in results.items():
        ok = [v for v in r["scenarios"].values() if "score" in v]
        dims = {}
        for d in DIMENSIONS:
            vals = [v["judge"][d] for v in ok if v.get("judge")]
            dims[d] = round(sum(vals) / len(vals), 2) if vals else None
        r["summary"] = {
            "overall": round(sum(v["score"] for v in ok) / len(ok), 1) if ok else None,
            "heuristic": round(sum(v["heuristic"]["score"] for v in ok) / len(ok), 1) if ok else None,
            "dimensions": dims, "n_ok": len(ok), "n_failed": len(r["scenarios"]) - len(ok),
            "judged": sum(1 for v in ok if v.get("judge")),
            "errors": sorted({v["error"] for v in r["scenarios"].values() if "error" in v})[:3],
        }
        out.append(r)
    out.sort(key=lambda r: -(r["summary"]["overall"] or -1))
    return {"models": out, "scenarios": [{"id": s["id"], "emotion": s["emotion"], "text": s["text"]} for s in scen],
            "judge": {"provider": judge_cfg["provider"], "model": judge_cfg["model"]} if judge_cfg else None,
            "method": "75% rubric judge (1–5 on four EPITOME-inspired dimensions) + 25% lexical heuristic; heuristic only when no judge is available."}
