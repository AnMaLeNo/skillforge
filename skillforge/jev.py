"""Client JEV (TypeSafe) via OpenRouter Decisions API.

Règles : modèle pinné, une requête = un state + N questions atomiques évaluées
indépendamment ; chaque appel est journalisé en JSONL (requête + réponse brute +
coût) et mis en cache par empreinte, pour re-seuiller sans rappeler l'API.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

MODEL = "typesafe/jev-1.13"
URL = "https://openrouter.ai/api/alpha/decisions"
RUNS = Path(os.environ.get("SKILLFORGE_RUNS", Path(__file__).resolve().parent.parent / "runs"))
LOG = RUNS / "jev_log.jsonl"
CACHE = RUNS / "jev_cache"
spent = 0.0  # $ cumulés par ce process (lecture : api.improve mesure un delta)


def set_store(store) -> None:
    """Journal et cache JEV dans un dossier fourni par le client (API) au lieu de runs/."""
    global LOG, CACHE
    from pathlib import Path as _P
    LOG, CACHE = _P(store) / "jev_log.jsonl", _P(store) / "jev_cache"
TOKEN_LIMIT = 32_000  # par question, défaut TypeSafe (au-delà : mode long contexte, moins précis)


def noul(instructions: str, true: str | None = None, false: str | None = None) -> dict:
    q: dict = {"type": "noul", "instructions": instructions}
    if true or false:
        q["criteria"] = {k: v for k, v in (("true", true), ("false", false)) if v}
    return q


def choice(instructions: str, criteria: dict[str, str]) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": dict(criteria)}


def score(instructions: str, levels: list[str]) -> dict:
    return {"type": "score", "instructions": instructions, "criteria": list(levels)}


def approx_tokens(obj) -> int:
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return len(s) // 3


def _fingerprint(model: str, state, questions: dict) -> str:
    raw = json.dumps({"m": model, "s": state, "q": questions}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def ask(state, questions: dict, *, tag: str = "", session_id: str | None = None,
        model: str = MODEL, use_cache: bool = True, timeout: float = 60) -> dict:
    """Envoie state + questions à JEV. Retourne le JSON brut (clé `answers`)."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY absent")
    n_tok = approx_tokens(state)
    if n_tok > TOKEN_LIMIT:
        raise ValueError(f"state ≈ {n_tok} tokens > {TOKEN_LIMIT} : découper avant d'appeler JEV")
    fp = _fingerprint(model, state, questions)
    CACHE.mkdir(parents=True, exist_ok=True)
    cpath = CACHE / f"{fp}.json"
    if use_cache and cpath.exists():
        return json.loads(cpath.read_text())["response"]

    body = {"model": model, "state": state, "questions": questions}
    if session_id:
        body["session_id"] = session_id
    req = urllib.request.Request(
        URL, data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/AnMaLeNo", "X-Title": "skillforge"},
        method="POST")
    t0 = time.time()
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.read()[:500]!r}"
            if e.code < 500 and e.code != 429:
                raise RuntimeError(last_err)
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = repr(e)
        time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError(f"JEV injoignable : {last_err}")
    ms = int((time.time() - t0) * 1000)
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "tag": tag, "fp": fp, "ms": ms,
           "state_tokens": n_tok, "request": body, "response": resp}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    cpath.write_text(json.dumps(rec, ensure_ascii=False))
    return resp


def answers(resp: dict) -> dict:
    return resp["answers"]


def total_cost() -> tuple[int, float]:
    """(nombre d'appels, coût cumulé $) depuis le journal."""
    if not LOG.exists():
        return 0, 0.0
    n, c = 0, 0.0
    for line in LOG.open():
        n += 1
        c += (json.loads(line)["response"].get("usage") or {}).get("cost", 0) or 0
    return n, c
