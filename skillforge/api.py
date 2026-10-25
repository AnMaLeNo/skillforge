"""API publique : improve(episode) -> Verdict, answer(...) -> AnswerResult, replay(...).
Tout l'état (historique Q/R, journal et cache JEV) vit dans `store`, un dossier fourni par le client."""
from __future__ import annotations

import difflib
import json
import tempfile
from pathlib import Path

from . import ambiguity, improve as _imp, jev, transcript
from .contract import (Answer, AnswerResult, Cost, Episode, Evidence, HistoryHit, Passage, Patch, Question, Verdict)
from .decide import BEHAV

SEP = "### skill "


def _steps(ep: Episode) -> list[transcript.Step]:
    if ep.trace.events is not None:
        steps = transcript.parse_events(ep.trace.events)
    elif ep.trace.path:
        steps = transcript.parse(Path(ep.trace.path))
    else:
        raise ValueError("trace.path ou trace.events requis")
    return [s for s in steps if not s.sidechain]


def _combined(ep: Episode) -> tuple[str, list[tuple[str, int]]]:
    """Texte unique (toutes les skills) + table ligne globale → (skill_id, ligne locale)."""
    parts, table = [], []
    for sk in ep.skills:
        parts.append(f"{SEP}{sk.id}"); table.append((sk.id, 0))
        for j, l in enumerate(sk.text.splitlines(), 1):
            parts.append(l); table.append((sk.id, j))
    return "\n".join(parts), table


def _passage(label: str | None, text: str, table) -> Passage | None:
    if not label or label == "none" or not label.startswith("L"):
        return None
    g = int(label[1:]); sid, loc = table[g - 1]
    if loc == 0:
        return None
    return Passage(skill_id=sid, line=loc, text=text)


def improve(ep: Episode, *, store: Path | str, draft_with_llm: bool = False, tag: str | None = None) -> Verdict:
    store = Path(store); store.mkdir(parents=True, exist_ok=True)
    jev.set_store(store)
    n0, c0 = jev.total_cost()
    try:
        steps = _steps(ep)
        text, table = _combined(ep)
        report = ep.agent_report.model_dump() if ep.agent_report else None
        res = _imp.analyse(text, steps, report, tag=tag or ep.id)
        x = res["features"]
        d = _imp.decide(x, _imp.TA, _imp.TR, _imp.TB)
        v = Verdict(episode_id=ep.id, decision=d, scores={k: round(float(val), 3) for k, val in x.items()})
        if d == "demander":
            pk = _imp.packet(res, steps, report)
            lab = next(iter(pk["passage"]), None) if pk.get("passage") else None
            v.passage = _passage(lab, (pk["passage"] or {}).get(lab, ""), table)
            v.why = pk["pourquoi"]
            v.evidence = [Evidence(**e) for e in pk["extraits_trace"]]
            q = {"text": pk["question"], "source": "code"}
            if draft_with_llm:
                dq = _imp.draft_question(pk, text, tag=tag or ep.id)
                q = {"text": dq["question"], "fact": dq["fait"], "source": "code" if dq["rejetee"] else "llm",
                     "checks": {"invente": dq["jev_invente"], "repondable": dq["jev_repondable"]}}
                v.cost.claude_usd += float(dq.get("cost_usd") or 0)
            v.question = Question(**q)
            if v.passage:
                need = (report or {}).get("needs_human") or pk["question"]
                hit = ambiguity.already_answered(v.passage.skill_id, need, tag=tag or ep.id, store=store)
                if hit["entry"]:
                    e = hit["entry"]
                    v.history_hit = HistoryHit(question=e["question"], answer=e["answer"], scope=e.get("scope"),
                                               probability=float(hit["probabilities"].get(hit["choice"], 0)))
                    if e.get("scope") == "general":
                        sk = next(s for s in ep.skills if s.id == v.passage.skill_id)
                        v.proposed_patch = _patch(sk.id, sk.text, e["answer"])
        elif d == "reformuler":
            lab = res["locate"]["choice"]
            v.passage = _passage(lab, res["lines"].get(lab, ""), table)
            v.behaviours = [k for k in BEHAV if x[k] >= _imp.TR]
            v.evidence = [Evidence(step=s.i, kind="assistant", text=s.text[:600]) for s in reversed(steps) if s.kind == "assistant" and s.text.strip()][:1]
    except Exception as e:  # le client ne doit jamais tomber à cause de skillforge
        v = Verdict(episode_id=ep.id, decision="indisponible", errors=[f"{type(e).__name__}: {e}"[:300]])
    n1, c1 = jev.total_cost()
    v.cost.jev_usd = round(c1 - c0, 6)
    return v


def _patch(skill_id: str, skill_text: str, answer: str) -> Patch:
    """Patch déterministe : la réponse générale de l'auteur est ajoutée telle quelle, sous un titre dédié (rien d'inventé)."""
    head = "## Précisions de l'auteur"
    lines = skill_text.rstrip("\n").splitlines()
    new = lines + ([""] if lines and lines[-1].strip() else []) + ([head] if head not in lines else []) + [f"- {answer.strip()}"]
    diff = difflib.unified_diff(lines, new, fromfile=f"{skill_id}/SKILL.md", tofile=f"{skill_id}/SKILL.md", lineterm="")
    return Patch(skill_id=skill_id, diff="\n".join(diff) + "\n")


def answer(a: Answer, *, store: Path | str, skill_text: str, tag: str | None = None) -> AnswerResult:
    """Enregistre la réponse de l'auteur dans l'historique de la skill ; JEV décide la portée si elle n'est pas donnée ;
    une réponse générale produit un patch (diff) à valider par l'humain."""
    store = Path(store); store.mkdir(parents=True, exist_ok=True)
    jev.set_store(store)
    sc = ambiguity.scope_of(skill_text, a.question, a.answer, tag=tag or a.skill_id)
    scope = a.scope or ("general" if sc["general"] >= 0.5 else "ponctuel")
    ambiguity.record_answer(a.skill_id, a.question, a.answer, run=a.episode_id, scope=scope, store=store)
    return AnswerResult(scope=scope, general_probability=sc["general"], contradicts_skill=sc["contradicts_skill"],
                        proposed_patch=_patch(a.skill_id, skill_text, a.answer) if scope == "general" else None)


def replay(episodes: list[Episode], *, store: Path | str) -> list[Verdict]:
    return [improve(e, store=store) for e in episodes]


def episode_from_files(skill_paths: list[Path], trace: Path, *, episode_id: str | None = None,
                       report: dict | None = None) -> Episode:
    """Client minimal : des SKILL.md + un transcript Claude Code (session .jsonl ou stream-json .log)."""
    from .contract import AgentReport, SkillRef, Trace
    fmt = "claude-session-jsonl" if trace.suffix == ".jsonl" else "claude-stream-json"
    return Episode(id=episode_id or trace.stem, skills=[SkillRef(id=(p.parent.name if p.name == "SKILL.md" else p.stem), text=p.read_text()) for p in skill_paths],
                   trace=Trace(format=fmt, path=str(trace)), agent_report=AgentReport(**report) if report else None)
