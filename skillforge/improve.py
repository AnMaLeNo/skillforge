"""`python -m skillforge.improve SKILL.md TRACE [--report run.json] [--out dossier] [--llm]`

Une skill + une trace (transcript Claude Code .jsonl, ou .log stream-json d'infra) → une décision :
  rien        : pas de problème attribuable à la skill ;
  reformuler  : passage accusé + preuves (rewrite.py sait produire les variantes et les faire départager par JEV) ;
  demander    : paquet pour l'auteur — ce que dit la skill (passage), ce que l'agent a fait/dit (extraits bruts),
                ce qu'il déclare lui manquer, et une question courte. Rien n'est inventé : sans --llm, le texte est
                assemblé par code à partir des extraits ; avec --llm, Sonnet (claude -p sans outil) rédige la question.
Seuils : ceux mesurés dans decide.py (held-out 0,80 sur 106 cas).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from . import ambiguity, detect, jev, transcript
from .decide import BEHAV, decide

TA, TR, TB = 0.85, 0.6, 0.85  # demander si manque/env ≥ TA ou (ambigu ≥ TB et comportement ≥ TR) ; reformuler si comportement ≥ TR
STALL = ("bloqu", "manque", "je suppose", "j'ai supposé", "je ne sais", "permission denied", "impossible", "précis",
         "ambigu", "contradict", "demande", "à décider", "needs_human")


def load_trace(path: Path) -> list[transcript.Step]:
    return [s for s in transcript.parse(path) if not s.sidechain]


def skill_lines(text: str) -> list[tuple[str, str]]:
    return [(f"L{i+1}", l) for i, l in enumerate(text.splitlines()) if l.strip() and not l.startswith("---")]


def analyse(skill_text: str, steps: list[transcript.Step], report: dict | None, *, tag: str) -> dict:
    lines = skill_lines(skill_text)
    state = {"skill": "\n".join(f"{k}: {v}" for k, v in lines),
             "transcript": transcript.render(steps, max_chars_per_step=800)}
    if len(state["transcript"]) > 70_000:
        t = state["transcript"]; state["transcript"] = t[:35_000] + "\n[... milieu coupé ...]\n" + t[-35_000:]
    if report:
        state["rapport_agent"] = {k: report.get(k) for k in ("status", "needs_human", "report") if report.get(k)}
    q = {**detect.QUESTIONS, **ambiguity.QUESTIONS, "locate": detect.locate_question(lines, False)}
    crit = {k: v[:200] for k, v in lines}
    crit["none"] = "Aucun passage de la skill n'est en cause (contexte suffisant, ou cause hors skill)."
    q["where"] = jev.choice("Quel passage de la skill aurait dû donner l'information manquante ou lever l'ambiguïté ?", crit)
    a = jev.answers(jev.ask(state, q, tag=f"improve:{tag}"))
    x = {k: a[k]["noul"] for k in (*BEHAV, *ambiguity.QUESTIONS)}
    x["p_none"] = a["locate"]["probabilities"].get("none", 0)
    return {"features": x, "locate": a["locate"], "where": a["where"], "lines": dict(lines)}


def extracts(steps, n=5) -> list[dict]:
    hits = []
    for s in steps:
        low = s.text.lower()
        is_dump = s.kind == "tool_result" and (len(s.text) > 500 and not re.search(r"denied|error|erreur|refused|cannot|conflict|fatal", low))
        if s.kind in ("assistant", "tool_result") and not is_dump and any(w in low for w in STALL):
            hits.append({"step": s.i, "kind": s.kind, "text": s.text.strip()[:700]})
        if s.kind == "tool_use":
            for t in s.tools:
                if t.get("name", "").endswith("run_report") or "needs_human" in json.dumps(t.get("input"), ensure_ascii=False):
                    hits.append({"step": s.i, "kind": "tool_use", "text": json.dumps(t.get("input"), ensure_ascii=False)[:900]})
    return hits[-n:]  # les derniers : c'est là que l'agent conclut / se bloque


def packet(res: dict, steps, report: dict | None) -> dict:
    x = res["features"]
    where = res["where"]["choice"]
    if where == "none":
        where = res["locate"]["choice"]
    why = []
    if x["blocked_by_env"] >= TA:
        why.append("l'agent a été arrêté par l'environnement (droits, accès, ressource absente) — ce n'est pas la skill qui peut le résoudre")
    if x["missing_context"] >= TA:
        why.append("l'agent a manqué d'une information que la skill ne donne pas")
    if x["ambiguous"] >= TB:
        why.append("la skill admet plusieurs lectures et l'agent a dû choisir")
    needs = (report or {}).get("needs_human")
    question = (f"L'agent demande : « {needs.strip()[:400]} » — quelle est la réponse, et vaut-elle pour tous les projets qui utilisent cette skill ?"
                if needs else
                f"Que doit faire l'agent dans la situation ci-dessus ? (précision à ajouter au passage {where} si la règle est générale)")
    return {"decision": "demander",
            "passage": {where: res["lines"].get(where, "")} if where != "none" else None,
            "pourquoi": why,
            "ce_que_l_agent_declare": needs,
            "extraits_trace": extracts(steps),
            "question": question,
            "scores": {k: round(v, 2) for k, v in x.items()}}


def render_md(p: dict) -> str:
    out = [f"## Décision : {p['decision']}"]
    if p.get("passage"):
        (k, v), = p["passage"].items(); out += [f"**Passage de la skill concerné ({k})** : {v}"]
    if p.get("pourquoi"):
        out += ["**Pourquoi on te demande** : " + " ; ".join(p["pourquoi"])]
    if p.get("ce_que_l_agent_declare"):
        out += ["**Ce que l'agent dit lui manquer** : " + p["ce_que_l_agent_declare"][:600]]
    if p.get("extraits_trace"):
        out += ["**Extraits bruts de la trace** :"] + [f"- [{e['step']} {e['kind']}] {e['text'][:300]}" for e in p["extraits_trace"]]
    if p.get("question"):
        out += ["", f"**Question** : {p['question']}"]
    if p.get("preuves"):
        out += ["**Preuves** : " + json.dumps(p["preuves"], ensure_ascii=False)[:800]]
    return "\n".join(out)


def improve(skill_path: Path, trace_path: Path, report_path: Path | None = None, *, tag: str | None = None) -> dict:
    skill_text = skill_path.read_text()
    steps = load_trace(trace_path)
    report = json.loads(report_path.read_text()) if report_path else None
    res = analyse(skill_text, steps, report, tag=tag or trace_path.stem[:40])
    x = res["features"]
    d = decide(x, TA, TR, TB)
    if d == "demander":
        return packet(res, steps, report)
    if d == "reformuler":
        acc = res["locate"]["choice"]
        flags = [k for k in BEHAV if x[k] >= TR]
        return {"decision": "reformuler", "passage": {acc: res["lines"].get(acc, "")}, "comportements": flags,
                "preuves": {"appels_outils": [f"{t['name']} {json.dumps(t.get('input'), ensure_ascii=False)[:120]}" for s in steps if s.kind == "tool_use" for t in s.tools][:12],
                            "derniere_reponse": next((s.text[:600] for s in reversed(steps) if s.kind == "assistant" and s.text.strip()), "")},
                "scores": {k: round(v, 2) for k, v in x.items()}}
    return {"decision": "rien", "scores": {k: round(v, 2) for k, v in x.items()}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("skill", type=Path); ap.add_argument("trace", type=Path)
    ap.add_argument("--report", type=Path); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = improve(a.skill, a.trace, a.report)
    print(json.dumps(r, ensure_ascii=False, indent=1) if a.json else render_md(r))
