"""Décision « rien / reformuler / demander » et sa mesure.

Jeu étiqueté : épisodes c1 (défaut injecté → `reformuler`, contradiction → `demander` car on ne peut pas savoir
quel fichier est le bon, sain → `rien`), hard1 (`rien`), runs infra (`bloqué` → `demander`, sinon `rien`).
Traits : 6 comportements (detect.QUESTIONS) + 3 questions contexte (ambiguity.QUESTIONS) + p(none) de la localisation.
Règle à deux seuils calibrée sur la moitié des tâches, mesurée sur l'autre moitié.
"""
from __future__ import annotations

import itertools
import json
import sys
from collections import Counter
from pathlib import Path

from . import ambiguity, detect, jev
from .infra_runs import RUNS as INFRA, compact, skill_text

OUT = Path(__file__).resolve().parent.parent / "runs" / "decide"
BEHAV = list(detect.QUESTIONS)
CTX = list(ambiguity.QUESTIONS)
LABELS = ("rien", "reformuler", "demander")


def label_c1(r: dict) -> str:
    return "rien" if not r["fault"] else ("demander" if r["fault"] == "contradiction" else "reformuler")


def features() -> list[dict]:
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "features.jsonl"
    done = {json.loads(l)["id"] for l in out.open()} if out.exists() else set()
    rows = []
    for camp in ("c1", "hard1"):
        jl = Path("runs/campaigns") / camp / "jev.jsonl"
        res = {json.loads(l)["episode_id"]: json.loads(l) for l in (Path("runs/campaigns") / camp / "results.jsonl").open()}
        for l in jl.open():
            r = json.loads(l)
            rid = f"{camp}:{r['episode_id']}"
            if rid in done:
                continue
            ep = Path(res[r["episode_id"]]["episode_dir"])
            st = detect.build_state(ep)
            a = jev.answers(jev.ask(st, dict(ambiguity.QUESTIONS), tag=f"decide:{rid}"))
            row = {"id": rid, "group": r["skill_task"], "label": label_c1(r) if camp == "c1" else "rien",
                   **{k: r["noul"][k] for k in BEHAV}, **{k: a[k]["noul"] for k in CTX}, "p_none": r["locate"].get("none", 0)}
            rows.append(row); out.open("a").write(json.dumps(row, ensure_ascii=False) + "\n"); print(rid, row["label"], flush=True)
    amb = {x["run"]: x for x in json.loads((INFRA.parent / "infra-ambiguity.json").read_text())}
    for rj in sorted(p for p in INFRA.glob("*.json") if p.with_suffix(".log").exists()):
        rid = f"infra:{rj.stem}"
        if rid in done:
            continue
        run = ambiguity.load_infra_run(rj); rec = run["rec"]
        st = {"skill": skill_text(rec["skills"]), "transcript": compact(run["steps"]),
              "rapport_agent": {k: rec.get(k) for k in ("status", "needs_human", "report") if rec.get(k)}}
        a = jev.answers(jev.ask(st, dict(detect.QUESTIONS), tag=f"decide:{rid}"))
        x = amb[rj.stem]
        row = {"id": rid, "group": "infra:" + rec["project"], "label": "demander" if rec.get("status") == "bloqué" or rec.get("status") is None else "rien",
               **{k: a[k]["noul"] for k in BEHAV}, **{k: x["flags"][k]["noul"] for k in CTX},
               "p_none": x["where"]["probabilities"].get("none", 0)}
        rows.append(row); out.open("a").write(json.dumps(row, ensure_ascii=False) + "\n"); print(rid, row["label"], flush=True)
    return [json.loads(l) for l in out.open()]


def decide(x: dict, ta: float, tr: float, tb: float = 1.01) -> str:
    """demander : il manque une info / l'environnement bloque, ou la skill est ambiguë (contradiction) ;
    reformuler : un comportement est détecté et la skill en est la cause ; sinon rien."""
    ask = max(x["missing_context"], x["blocked_by_env"])
    beh = max(x[k] for k in BEHAV)
    if ask >= ta or (x["ambiguous"] >= tb and beh >= tr):
        return "demander"
    if beh >= tr:
        return "reformuler"
    return "rien"


def confusion(rows, ta, tr, tb=1.01) -> tuple[Counter, float]:
    """(matrice, exactitude équilibrée = moyenne des rappels par classe : les classes rares comptent autant)."""
    c = Counter((x["label"], decide(x, ta, tr, tb)) for x in rows)
    recalls = [c[(l, l)] / n for l in LABELS if (n := sum(v for (a, _), v in c.items() if a == l))]
    return c, sum(recalls) / len(recalls)


def fmt(c: Counter) -> str:
    head = "vrai \\ décidé  " + "  ".join(f"{l:>10s}" for l in LABELS)
    body = [f"{a:14s} " + "  ".join(f"{c[(a, b)]:10d}" for b in LABELS) for a in LABELS]
    return "\n".join([head, *body])


def evaluate(rows):
    groups = sorted({x["group"] for x in rows})
    lines = [f"cas : {len(rows)} ({dict(Counter(x['label'] for x in rows))})"]
    grid = [i / 20 for i in range(2, 20)]
    for name, cal_g in (("A (tâches paires → impaires)", set(groups[::2])), ("B (impaires → paires)", set(groups[1::2]))):
        cal = [x for x in rows if x["group"] in cal_g]; held = [x for x in rows if x["group"] not in cal_g]
        best = max(((confusion(cal, ta, tr, tb)[1], -abs(ta - 0.5), ta, tr, tb) for ta, tr, tb in itertools.product(grid, grid, grid)))
        _, _, ta, tr, tb = best
        lines += [f"\n#### split {name} : calibration {len(cal)} / held-out {len(held)}",
                  f"seuils : demander si max(manque_info, environnement) ≥ {ta} ou (ambiguïté ≥ {tb} et comportement ≥ {tr}) ; sinon reformuler si comportement ≥ {tr}",
                  f"== calibration (exactitude équilibrée {confusion(cal, ta, tr, tb)[1]:.2f})\n{fmt(confusion(cal, ta, tr, tb)[0])}",
                  f"== held-out (exactitude équilibrée {confusion(held, ta, tr, tb)[1]:.2f})\n{fmt(confusion(held, ta, tr, tb)[0])}",
                  "== erreurs held-out"]
        lines += [f"  {x['id'][:50]:50s} vrai={x['label']:10s} décidé={decide(x, ta, tr, tb):10s} manque={x['missing_context']:.2f} env={x['blocked_by_env']:.2f} "
                  f"ambigu={x['ambiguous']:.2f} comport_max={max(x[k] for k in BEHAV):.2f} ({max(BEHAV, key=lambda k: x[k])})"
                  for x in held if decide(x, ta, tr, tb) != x["label"]]
    return "\n".join(lines)
    for x in []:
        d = decide(x, ta, tr)
        if d != x["label"]:
            lines.append(f"  {x['id'][:50]:50s} vrai={x['label']:10s} décidé={d:10s} manque={x['missing_context']:.2f} env={x['blocked_by_env']:.2f} "
                         f"ambigu={x['ambiguous']:.2f} comport_max={max(x[k] for k in BEHAV):.2f} ({max(BEHAV, key=lambda k: x[k])})")
    return "\n".join(lines)


if __name__ == "__main__":
    rows = features()
    rep = evaluate(rows)
    (OUT / "report.txt").write_text(rep)
    print(rep)
