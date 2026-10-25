"""Manque de contexte / ambiguïté dans une skill → question à l'auteur.

Hypothèse de l'utilisateur : quand Sonnet rate ou se bloque, la skill était ambiguë ou incomplète ; la seule
correction fiable est une précision de l'auteur. Ce module :
  1. lit un run réel (infra : runs/<run>.json + .log stream-json, ou un épisode skillforge) ;
  2. demande à JEV (questions atomiques) si l'agent a manqué d'une information que la skill aurait dû donner,
     s'il a dû choisir entre plusieurs lectures, et quel passage de la skill est concerné ;
  3. vérifie dans l'historique Q/R de la skill si une réponse déjà donnée couvre le besoin (JEV Choice) ;
  4. sinon prépare le paquet pour l'auteur : extraits bruts (skill, trace) + question courte (rédaction par
     claude -p sans outil, appel facultatif et compté).
Rien ici ne modifie la skill : la réponse de l'auteur est stockée et c'est rewrite.py qui l'utilise.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import jev, transcript
from .detect import skill_lines

HIST = Path(__file__).resolve().parent.parent / "runs" / "qa_history.jsonl"

QUESTIONS = {
    "missing_context": jev.noul(
        "L'agent a eu besoin d'une information (accès, nom, valeur, droit, décision) que la skill ne donne pas, "
        "et cela l'a empêché de finir ou l'a fait deviner.",
        true="L'agent écrit qu'il lui manque quelque chose, demande une précision, se déclare bloqué, ou choisit une valeur en disant qu'il suppose.",
        false="L'agent avait tout ce qu'il fallait dans la skill et le dépôt ; il n'a rien supposé ni demandé."),
    "ambiguous": jev.noul(
        "Un passage de la skill admet plusieurs lectures raisonnables et l'agent a dû en choisir une.",
        true="L'agent hésite explicitement entre deux interprétations, ou sa lecture contredit un autre passage de la skill.",
        false="Chaque consigne de la skill n'a qu'une lecture possible dans ce contexte."),
    "blocked_by_env": jev.noul(
        "Le blocage vient de l'environnement (droits, réseau, secret absent, dépôt privé) et non du texte de la skill.",
        true="Une commande échoue pour une raison d'accès ou d'absence de ressource que la skill ne pouvait pas changer.",
        false="Aucune erreur d'accès ou de ressource ; le problème est dans ce que la skill demande ou omet."),
}


def load_infra_run(run_json: Path) -> dict:
    """Un run infra : rec (prompt, skills, before/after, status, needs_human, report) + steps du .log stream-json."""
    rec = json.loads(run_json.read_text())
    log = run_json.with_suffix(".log")
    steps = transcript.parse(log) if log.exists() else []
    return {"rec": rec, "steps": steps}


def build_state(skill_text: str, steps: list[transcript.Step], rec: dict | None = None) -> dict:
    lines = [(f"L{i+1}", l) for i, l in enumerate(skill_text.splitlines())]
    st = {"skill": "\n".join(f"{k}: {v}" for k, v in lines),
          "trace": transcript.render(steps, max_chars_per_step=1200)}
    if rec:
        st["rapport_agent"] = {k: rec.get(k) for k in ("status", "needs_human", "report", "result") if rec.get(k)}
    return st, lines


def analyse(skill_text: str, steps: list[transcript.Step], rec: dict | None = None, *, tag: str = "") -> dict:
    st, lines = build_state(skill_text, steps, rec)
    q = dict(QUESTIONS)
    crit = {k: v[:200] for k, v in lines if v.strip()}
    crit["none"] = "Aucun passage de la skill n'est en cause (contexte suffisant, ou cause hors skill)."
    q["where"] = jev.choice("Quel passage de la skill aurait dû donner l'information manquante ou lever l'ambiguïté ?", crit)
    a = jev.answers(jev.ask(st, q, tag=f"ambig:{tag}"))
    return {"flags": {k: a[k] for k in QUESTIONS}, "where": a["where"], "lines": dict(lines)}


def _hist(store=None) -> Path:
    return Path(store) / "qa_history.jsonl" if store else HIST


def history(skill_id: str, store=None) -> list[dict]:
    """Entrées Q/R de la skill (clé = chemin de skill, ex. `expose/public`), dans l'ordre d'enregistrement."""
    h = _hist(store)
    if not h.exists():
        return []
    return [e for e in (json.loads(l) for l in h.read_text().splitlines() if l.strip()) if e["skill"] == skill_id]


def already_answered(skill_id: str, need: str, *, tag: str = "", store=None) -> dict:
    """JEV : une réponse déjà donnée par l'auteur couvre-t-elle ce besoin ? Choice sur l'historique + `none`.
    Renvoie {entry|None, choice, probabilities} ; sans historique → entry None sans appel."""
    h = history(skill_id, store)
    if not h:
        return {"entry": None, "choice": "none", "probabilities": {}}
    crit = {f"R{i+1}": f"Question : {e['question'][:200]} / Réponse de l'auteur : {e['answer'][:250]}" for i, e in enumerate(h)}
    crit["none"] = "Aucune réponse précédente ne donne l'information dont l'agent a manqué."
    a = jev.answers(jev.ask({"besoin_de_l_agent": need, "historique_de_la_skill": crit}, {"pick": jev.choice(
        "Quelle réponse de l'auteur donne déjà l'information dont l'agent a manqué dans ce run ?", crit)},
        tag=f"hist:{skill_id}:{tag}"))["pick"]
    c = a["choice"]
    return {"entry": None if c == "none" else h[int(c[1:]) - 1], "choice": c, "probabilities": a["probabilities"]}


def scope_of(skill_text: str, question: str, answer: str, *, tag: str = "") -> dict:
    """JEV : la réponse est-elle une règle générale (à intégrer à la skill) ou propre à ce projet/cette fois ?"""
    a = jev.answers(jev.ask({"skill": skill_text, "question": question, "reponse_auteur": answer}, {
        "general": jev.noul(
            "La réponse énonce une règle qui vaudrait pour n'importe quel projet utilisant cette skill.",
            true="La réponse ne dépend d'aucun nom de projet, date, machine ou chemin particulier, ou énonce une condition générale.",
            false="La réponse autorise ou décrit une action pour un projet, un hôte ou un moment précis."),
        "contradicts_skill": jev.noul(
            "La réponse contredit un passage de la skill.",
            true="La skill interdit ou déconseille ce que la réponse autorise, ou l'inverse.",
            false="La réponse précise ou complète la skill sans la contredire."),
    }, tag=f"scope:{tag}"))
    return {k: a[k]["noul"] for k in ("general", "contradicts_skill")}


def record_answer(skill_id: str, question: str, answer: str, *, passage: str | None = None,
                  run: str | None = None, scope: str | None = None, store=None) -> None:
    h = _hist(store)
    h.parent.mkdir(parents=True, exist_ok=True)
    with h.open("a") as f:
        f.write(json.dumps({"skill": skill_id, "question": question, "answer": answer, "passage": passage,
                            "run": run, "scope": scope}, ensure_ascii=False) + "\n")


def packet(skill_text: str, steps: list[transcript.Step], res: dict, rec: dict | None = None, n_steps: int = 6) -> dict:
    """Le minimum à montrer à l'auteur : passage accusé, extraits bruts de la trace où l'agent bute, rapport de l'agent."""
    where = res["where"].get("top")
    hits = [s for s in steps if s.kind in ("assistant", "tool_result") and any(
        w in s.text.lower() for w in ("bloqu", "manque", "suppos", "je ne sais", "permission denied", "impossible", "précis", "ambigu"))]
    return {"passage": {where: res["lines"].get(where)} if where and where != "none" else None,
            "extraits": [{"i": s.i, "kind": s.kind, "text": s.text[:600]} for s in hits[:n_steps]],
            "rapport_agent": (rec or {}).get("needs_human") or (rec or {}).get("report"),
            "flags": res["flags"]}
