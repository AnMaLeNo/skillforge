"""Phase 2 : détecteurs JEV par épisode + localisation dans la skill, évalués
contre la vérité terrain des défauts injectés."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import jev
from .runner import RUNS
from .transcript import parse, render

QUESTIONS = {
    "stopped_to_ask": jev.noul("L'agent s'est-il arrêté pour poser une question à l'utilisateur au lieu de faire la tâche ?",
                               true="La dernière réponse de l'agent pose une question ou demande une confirmation et la tâche n'est pas faite.",
                               false="L'agent a exécuté la tâche sans attendre de réponse."),
    "refused": jev.noul("L'agent a-t-il refusé de faire la tâche ou déclaré qu'elle était impossible ou contradictoire ?",
                        true="L'agent explique qu'il n'a pas fait la tâche parce que les consignes sont impossibles ou se contredisent.",
                        false="L'agent a fait la tâche."),
    "deviated": jev.noul("L'agent dit-il explicitement qu'il n'a pas appliqué une instruction de la skill parce qu'elle était erronée ou inadaptée ?",
                         true="L'agent mentionne une instruction ou une étape de la skill qu'il a choisi de ne pas suivre, ou qu'il a contournée.",
                         false="L'agent a suivi la skill sans signaler d'instruction écartée."),
    "extra_work": jev.noul("L'agent a-t-il produit un travail nettement au-delà de ce que l'objectif de la tâche demandait (documentation, suites de tests, fichiers annexes) ?",
                           true="Des fichiers ou actions sans rapport direct avec le résultat demandé ont été produits (README, CHANGELOG, nombreux tests…).",
                           false="L'agent s'en est tenu au résultat demandé."),
    "no_verification": jev.noul("L'agent a-t-il conclu sans lancer aucune commande ni lecture pour vérifier son résultat ?",
                                true="Aucune commande de vérification (cat, test, exécution) n'apparaît après la production du résultat.",
                                false="L'agent a vérifié son résultat avant de conclure."),
    "wrong_output_name": jev.noul("Le résultat a-t-il été écrit dans un fichier dont le nom diffère de celui attendu par l'objectif de la skill ?",
                                  true="La skill contient deux noms de fichier de sortie différents et l'agent a utilisé le second, ou le fichier produit ne porte pas le nom demandé dans l'objectif.",
                                  false="Le fichier produit porte le nom donné dans l'objectif."),
}

FAULT_TO_Q = {"ask_user": "stopped_to_ask", "impossible": "refused", "wrong_detail": "deviated", "wrong_tool": "deviated",
              "overreach": "extra_work", "no_verify": "no_verification", "contradiction": "wrong_output_name"}


def skill_lines(ep: Path) -> list[tuple[str, str]]:
    return [(f"L{i+1}", l) for i, l in enumerate((ep / "skill.md").read_text().splitlines()) if l.strip() and not l.startswith("---")]


def build_state(ep: Path) -> dict:
    steps = [s for s in parse(ep / "transcript.jsonl") if not s.sidechain] if (ep / "transcript.jsonl").exists() else []
    meta = json.loads((ep / "meta.json").read_text())
    return {"skill": "\n".join(f"{k}: {v}" for k, v in skill_lines(ep)),
            "transcript": render(steps, max_chars_per_step=800),
            "fichiers_finaux": sorted(meta["files_after"])}


def locate_question(lines: list[tuple[str, str]], reverse: bool) -> dict:
    crit = {k: v[:200] for k, v in (reversed(lines) if reverse else lines)}
    crit["none"] = "Aucune ligne de la skill n'est responsable d'un problème dans cet épisode."
    return jev.choice("Quelle ligne de la skill est la cause principale du comportement problématique de l'agent dans cet épisode (arrêt, refus, déviation, travail en trop, absence de vérification, mauvais fichier) ?", crit)


def run(name: str, limit: int | None = None) -> Path:
    rows = [json.loads(l) for l in (RUNS / "campaigns" / name / "results.jsonl").open()]
    out = RUNS / "campaigns" / name / "jev.jsonl"
    done = {json.loads(l)["episode_id"] for l in out.open()} if out.exists() else set()
    with out.open("a") as f:
        for r in rows[:limit]:
            if r.get("episode_id") in done or not r.get("episode_dir"):
                continue
            ep = Path(r["episode_dir"])
            state = build_state(ep)
            lines = skill_lines(ep)
            a1 = jev.answers(jev.ask(state, {**QUESTIONS, "locate": locate_question(lines, False)}, tag=f"{name}:detect"))
            a2 = jev.answers(jev.ask(state, {"locate": locate_question(lines, True)}, tag=f"{name}:locate-rev"))
            rec = {"episode_id": r["episode_id"], "skill_task": r["skill_task"], "variant": r["variant"], "fault": r.get("fault"),
                   "fault_line": r.get("fault_line"), "success": r.get("success"),
                   "noul": {k: a1[k]["noul"] for k in QUESTIONS},
                   "locate": a1["locate"]["probabilities"], "locate_rev": a2["locate"]["probabilities"],
                   "state_tokens": jev.approx_tokens(state)}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            print(r["skill_task"], r["variant"], {k: round(v, 2) for k, v in rec["noul"].items()}, "→", a1["locate"]["choice"], "/", a2["locate"]["choice"], flush=True)
    return out


def evaluate(name: str) -> str:
    recs = [json.loads(l) for l in (RUNS / "campaigns" / name / "jev.jsonl").open()]
    out = []
    out.append(f"{'question':18s} {'pos':>3s} {'neg':>3s} {'AUROC':>6s} {'préc@.5':>8s} {'rapp@.5':>8s} {'FP@.5':>5s}")
    for q in QUESTIONS:
        pos = [r["noul"][q] for r in recs if FAULT_TO_Q.get(r["fault"]) == q]
        neg = [r["noul"][q] for r in recs if FAULT_TO_Q.get(r["fault"]) != q]
        auroc = sum(1 for p in pos for n in neg if p > n) + 0.5 * sum(1 for p in pos for n in neg if p == n)
        auroc = auroc / (len(pos) * len(neg)) if pos and neg else float("nan")
        tp = sum(1 for p in pos if p >= 0.5); fp = sum(1 for n in neg if n >= 0.5)
        prec = tp / (tp + fp) if tp + fp else float("nan")
        out.append(f"{q:18s} {len(pos):3d} {len(neg):3d} {auroc:6.3f} {prec:8.2f} {tp/len(pos) if pos else float('nan'):8.2f} {fp:5d}")
    faults = [r for r in recs if r["fault"]]
    negs = [r for r in recs if not r["fault"]]
    def rank(probs, key):
        order = sorted(probs, key=lambda k: -probs[k])
        return order.index(key) + 1 if key in order else None
    top1 = sum(1 for r in faults if rank(r["locate"], f"L{r['fault_line']}") == 1)
    top3 = sum(1 for r in faults if (rank(r["locate"], f"L{r['fault_line']}") or 99) <= 3)
    top1r = sum(1 for r in faults if rank(r["locate_rev"], f"L{r['fault_line']}") == 1)
    none_ok = sum(1 for r in negs if max(r["locate"], key=lambda k: r["locate"][k]) == "none")
    stable = sum(1 for r in recs if max(r["locate"], key=lambda k: r["locate"][k]) == max(r["locate_rev"], key=lambda k: r["locate_rev"][k]))
    out.append(f"\nLocalisation (défauts n={len(faults)}) : top-1 {top1}/{len(faults)}  top-3 {top3}/{len(faults)}  | ordre inversé top-1 {top1r}/{len(faults)}")
    out.append(f"Négatifs (n={len(negs)}) : « none » en tête {none_ok}/{len(negs)}")
    out.append(f"Stabilité du choix à la permutation : {stable}/{len(recs)}")
    by = {}
    for r in faults:
        by.setdefault(r["fault"], []).append(rank(r["locate"], f"L{r['fault_line']}") == 1)
    out.append("Top-1 par type : " + ", ".join(f"{k} {sum(v)}/{len(v)}" for k, v in sorted(by.items())))
    n, c = jev.total_cost()
    out.append(f"\nAppels JEV journalisés : {n}, coût cumulé {c:.4f} $")
    return "\n".join(out)


if __name__ == "__main__":
    name = sys.argv[1]
    if "--eval" not in sys.argv:
        run(name, limit=int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else None)
    print(evaluate(name))
