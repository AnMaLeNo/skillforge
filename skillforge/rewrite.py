"""Phase 3 : réécriture des skills fautives (claude -p, 2 axes, sans outil),
sélection JEV par paires en aveugle, ré-exécution de la gagnante.

La vérité terrain (type/ligne du défaut) n'est jamais donnée au réécrivain ni à
JEV : seuls les constats de la phase 2 (ligne accusée, questions Noul ≥ 0,5,
extrait du transcript) sont utilisés."""
from __future__ import annotations

import itertools
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from . import jev
from .campaign import check
from .detect import QUESTIONS, build_state, skill_lines
from .metrics import compute
from .runner import CONFIG_DIR, MODEL, RUNS, run_episode
from .transcript import parse

LABELS = {"stopped_to_ask": "l'agent s'est arrêté pour poser une question à l'utilisateur au lieu de faire la tâche",
          "refused": "l'agent a refusé la tâche ou l'a déclarée impossible/contradictoire",
          "deviated": "l'agent a dû écarter explicitement une instruction de la skill pour réussir",
          "extra_work": "l'agent a produit du travail au-delà de l'objectif (fichiers annexes, tests, docs)",
          "no_verification": "l'agent a conclu sans rien vérifier",
          "wrong_output_name": "l'agent a écrit le résultat dans un fichier dont le nom ne correspond pas à l'objectif"}

AXES = {
    "A": "Reformule le passage accusé pour qu'il décrive l'OBJECTIF et le contexte (ce qu'il faut obtenir et pourquoi) au lieu d'imposer une façon de faire, en gardant toutes les informations nécessaires à la tâche (fichiers d'entrée et de sortie, format attendu).",
    "B": "Supprime ou assouplis le passage accusé (et toute phrase qui en dépend) sans rien ajouter d'autre ; le reste de la skill doit rester identique au mot près.",
}


def llm(prompt: str, *, budget: float = 0.2, timeout: int = 300) -> tuple[str, dict]:
    cmd = ["claude", "-p", prompt, "--model", MODEL, "--output-format", "json", "--tools", "", "--max-turns", "1",
           "--max-budget-usd", str(budget), "--setting-sources", ""]
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = str(CONFIG_DIR)
    for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
        env.pop(k, None)
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout, cwd="/tmp")
    d = json.loads(p.stdout) if p.stdout.strip().startswith("{") else {"result": p.stdout, "stderr": p.stderr[-500:]}
    return d.get("result") or "", d


def extract_skill(text: str) -> str | None:
    m = re.search(r"```(?:markdown|md)?\n(.*?)```", text, re.S)
    return m.group(1).strip() + "\n" if m else None


def evidence(rec: dict, res: dict) -> dict:
    ep = Path(res["episode_dir"])
    steps = [s for s in parse(ep / "transcript.jsonl") if not s.sidechain]
    calls = [f"{t['name']} {json.dumps(t.get('input'), ensure_ascii=False)[:160]}" for s in steps if s.kind == "tool_use" for t in s.tools]
    flags = [k for k, v in rec["noul"].items() if v >= 0.5]
    accused = max(rec["locate"], key=rec["locate"].get)
    lines = dict(skill_lines(ep))
    return {"accused": accused, "accused_text": lines.get(accused, ""), "flags": flags,
            "problems": "; ".join(LABELS[k] for k in flags) or "comportement non optimal",
            "calls": calls, "final": (res.get("final_text") or "")[:1200], "files": sorted(res.get("files_after") or []),
            "success": res.get("success")}


def rewrite_prompt(skill: str, ev: dict, axis: str) -> str:
    return f"""Tu améliores une skill (instructions données seules à un agent de code, sans autre contexte utilisateur).

SKILL ACTUELLE :
```markdown
{skill}```

CE QUI S'EST PASSÉ quand un agent l'a suivie :
- Problème(s) constaté(s) : {ev['problems']}.
- Passage de la skill identifié comme cause probable : {ev['accused']} « {ev['accused_text']} »
- Actions de l'agent : {json.dumps(ev['calls'], ensure_ascii=False)}
- Fichiers finaux : {ev['files']} ; vérification automatique de la tâche : {'réussie' if ev['success'] else 'échouée'}
- Réponse finale de l'agent : « {ev['final']} »

CONSIGNE DE RÉÉCRITURE : {AXES[axis]}

Réponds uniquement avec la skill complète réécrite dans un bloc ```markdown, sans commentaire."""


def select(cands: dict[str, str], ev: dict, tag: str) -> dict:
    """Paires en aveugle (X/Y), les deux ordres ; + 2 Noul de garde par candidat."""
    names = list(cands)
    wins = {n: 0.0 for n in names}
    log = []
    for a, b in itertools.combinations(names, 2):
        for first, second in ((a, b), (b, a)):
            q = jev.choice(f"Deux versions d'une skill. Dans un épisode précédent, {ev['problems']}. Laquelle des deux est la MOINS susceptible de reproduire ce comportement, tout en permettant d'accomplir la tâche ?",
                           {"X": "La skill X", "Y": "La skill Y"})
            r = jev.answers(jev.ask({"skill_X": cands[first], "skill_Y": cands[second]}, {"pick": q}, tag=f"{tag}:pair"))["pick"]["probabilities"]
            wins[first] += r["X"]; wins[second] += r["Y"]
            log.append({"X": first, "Y": second, "pX": r["X"]})
    guards = {}
    for n in names:
        g = jev.answers(jev.ask({"skill": cands[n]}, {
            "still_pushes": jev.noul(f"Cette skill contient-elle encore une instruction qui pousserait un agent à ce comportement : {ev['problems']} ?"),
            "goal_complete": jev.noul("Cette skill indique-t-elle clairement le résultat attendu (fichier(s) de sortie et contenu/format) pour qu'un agent puisse réussir la tâche sans autre information ?"),
        }, tag=f"{tag}:guard"))
        guards[n] = {k: g[k]["noul"] for k in ("still_pushes", "goal_complete")}
    score = {n: wins[n] / (2 * (len(names) - 1)) - 0.5 * guards[n]["still_pushes"] + 0.5 * guards[n]["goal_complete"] for n in names}
    return {"winner": max(score, key=score.get), "score": score, "wins": wins, "guards": guards, "pairs": log}


def pick_targets(name: str) -> list[tuple[dict, dict]]:
    recs = [json.loads(l) for l in (RUNS / "campaigns" / name / "jev.jsonl").open()]
    res = {r["episode_id"]: r for r in map(json.loads, (RUNS / "campaigns" / name / "results.jsonl").open())}
    best = {}
    for r in recs:
        if not r["fault"]:
            continue
        sev = max(r["noul"].values())
        if r["skill_task"] not in best or sev > best[r["skill_task"]][0]:
            best[r["skill_task"]] = (sev, r)
    return [(r, res[r["episode_id"]]) for _, r in sorted(best.values(), key=lambda x: x[1]["skill_task"])]


def run(name: str, limit: int | None = None, budget: float = 0.6):
    out_dir = RUNS / "campaigns" / name / "rewrites"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = out_dir / "results.jsonl"
    done = {json.loads(l)["skill_task"] for l in results.open()} if results.exists() else set()
    for rec, res in pick_targets(name)[:limit]:
        task = rec["skill_task"]
        if task in done:
            continue
        ep = Path(res["episode_dir"])
        d = out_dir / f"{task}--{rec['variant']}"
        d.mkdir(exist_ok=True)
        orig = (ep / "skill.md").read_text()
        ev = evidence(rec, res)
        (d / "evidence.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1))
        cands = {"orig": orig}
        llm_cost = 0.0
        for axis in AXES:
            p = d / f"{axis}.md"
            if not p.exists():
                text, raw = llm(rewrite_prompt(orig, ev, axis))
                llm_cost += raw.get("total_cost_usd") or 0
                sk = extract_skill(text)
                (d / f"{axis}.raw.txt").write_text(text)
                if sk:
                    p.write_text(sk)
            if p.exists():
                cands[axis] = p.read_text()
        sel = select(cands, ev, tag=f"{name}:rw:{task}")
        (d / "selection.json").write_text(json.dumps(sel, ensure_ascii=False, indent=1))
        row = {"skill_task": task, "variant": rec["variant"], "fault": rec["fault"], "fault_line": rec["fault_line"],
               "accused": ev["accused"], "flags": ev["flags"], "winner": sel["winner"], "score": sel["score"],
               "orig_success": res.get("success"), "rewrite_cost_usd": llm_cost}
        if sel["winner"] != "orig":
            meta = json.loads((Path("skills") / task / "task.json").read_text())
            ep2 = run_episode(d / f"{sel['winner']}.md", meta["task"], max_budget_usd=budget, seed_files=meta["seed_files"],
                              episode_id=f"{task}--rw{sel['winner']}--{time.strftime('%H%M%S')}")
            m = compute(ep2)
            m["success"] = check(ep2 / "work", meta["check"])
            a = jev.answers(jev.ask(build_state(ep2), dict(QUESTIONS), tag=f"{name}:rw:recheck"))
            row.update({"rerun_episode": str(ep2), "rerun_success": m["success"], "rerun_cost_usd": m.get("cost_usd"),
                        "rerun_tool_calls": m.get("tool_calls"), "rerun_noul": {k: a[k]["noul"] for k in QUESTIONS},
                        "rerun_flags": [k for k in QUESTIONS if a[k]["noul"] >= 0.5]})
        with results.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(task, rec["variant"], "accusé", ev["accused"], "→ gagnant", sel["winner"], {k: round(v, 2) for k, v in sel["score"].items()},
              "| relance ok=", row.get("rerun_success"), "flags", row.get("rerun_flags"), flush=True)


def report(name: str) -> str:
    rows = [json.loads(l) for l in (RUNS / "campaigns" / name / "rewrites" / "results.jsonl").open()]
    out = [f"{len(rows)} skills traitées ; gagnant : " + ", ".join(f"{w} {sum(1 for r in rows if r['winner']==w)}" for w in ("orig", "A", "B"))]
    rr = [r for r in rows if "rerun_success" in r]
    out.append(f"Ré-exécutions : {len(rr)} ; réussite code avant {sum(1 for r in rr if r['orig_success'])}/{len(rr)} → après {sum(1 for r in rr if r['rerun_success'])}/{len(rr)}")
    out.append(f"Comportement signalé disparu (aucun flag JEV à la relance) : {sum(1 for r in rr if not r['rerun_flags'])}/{len(rr)} ; flags persistants : {sum(1 for r in rr if set(r['rerun_flags']) & set(r['flags']))}/{len(rr)}")
    out.append(f"Coût Claude : réécritures {sum(r['rewrite_cost_usd'] for r in rows):.2f} $ + relances {sum(r.get('rerun_cost_usd') or 0 for r in rows):.2f} $")
    out.append("\n" + f"{'tâche':14s} {'défaut':14s} {'accusé/vrai':11s} {'gagnant':7s} {'ok avant→après':14s} flags après")
    for r in rows:
        out.append(f"{r['skill_task']:14s} {r['fault']:14s} {r['accused']+'/L'+str(r['fault_line']):11s} {r['winner']:7s} {str(r['orig_success'])+'→'+str(r.get('rerun_success','-')):14s} {r.get('rerun_flags','-')}")
    return "\n".join(out)


if __name__ == "__main__":
    name = sys.argv[1]
    if "--report" not in sys.argv:
        run(name, limit=int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else None)
    print(report(name))
