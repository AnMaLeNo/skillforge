"""Analyse des runs réels de l'outil `infra` (Pi) : runs/infra/<run>.json + .log, skills du clone ~/repos/infra."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import ambiguity, jev, transcript

RUNS = Path(__file__).resolve().parent.parent / "runs" / "infra"
SKILLS = Path.home() / "repos" / "infra" / "skills"


def skill_text(names: list[str]) -> str:
    parts = []
    for n in names:
        p = SKILLS / n / "SKILL.md"
        parts.append(f"### skill {n}\n" + (p.read_text() if p.exists() else "(introuvable)"))
    return "\n".join(parts)


def compact(steps, budget_chars=70_000):
    keep = [s for s in steps if s.kind in ("assistant", "tool_use", "tool_result") and not s.sidechain]
    txt = transcript.render(keep, max_chars_per_step=700)
    if len(txt) > budget_chars:
        h = budget_chars // 2
        txt = txt[:h] + "\n[... milieu de la trace coupé ...]\n" + txt[-h:]
    return txt


def main(limit=None):
    out = []
    for rj in sorted(p for p in RUNS.glob("*.json") if p.with_suffix(".log").exists())[:limit]:
        run = ambiguity.load_infra_run(rj)
        rec, steps = run["rec"], run["steps"]
        sk = skill_text(rec["skills"])
        lines = [(f"L{i+1}", l) for i, l in enumerate(sk.splitlines())]
        st = {"skill": "\n".join(f"{k}: {v}" for k, v in lines), "trace": compact(steps),
              "rapport_agent": {k: rec.get(k) for k in ("status", "needs_human", "report") if rec.get(k)}}
        q = dict(ambiguity.QUESTIONS)
        crit = {k: v[:200] for k, v in lines if v.strip() and not v.startswith("---")}
        crit["none"] = "Aucun passage de la skill n'est en cause (contexte suffisant, ou cause hors skill)."
        q["where"] = jev.choice("Quel passage de la skill aurait dû donner l'information manquante ou lever l'ambiguïté ?", crit)
        try:
            a = jev.answers(jev.ask(st, q, tag=f"infra:{rj.stem[:40]}"))
        except Exception as e:
            print(rj.stem[:45], "ERREUR", str(e)[:200]); continue
        flags = {k: a[k] for k in ambiguity.QUESTIONS}
        w = a["where"]
        top = w.get("choice") if isinstance(w, dict) else w
        print(f"{rj.stem[:45]:45s} status={rec.get('status')!s:7s} turns={rec.get('num_turns')} flags={flags} where={top}")
        if top and top != "none":
            print("    →", dict(lines).get(top, "")[:160])
        if rec.get("needs_human"):
            print("    needs_human:", rec["needs_human"][:200].replace("\n", " "))
        out.append({"run": rj.stem, "status": rec.get("status"), "flags": flags, "where": w, "line": dict(lines).get(top)})
    (RUNS.parent / "infra-ambiguity.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
