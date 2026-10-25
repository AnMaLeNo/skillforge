"""Campagne : lance chaque skill du corpus (ou une sélection), vérifie le résultat
par la commande `check` de la tâche, calcule les métriques code, et écrit
runs/campaigns/<nom>/results.jsonl (une ligne par épisode)."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .corpus import ROOT
from .metrics import compute
from .runner import RUNS, run_episode


def check(work: Path, cmd: str) -> bool:
    try:
        return subprocess.run(cmd, shell=True, cwd=work, capture_output=True, timeout=60).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def list_skills(tasks: list[str] | None, variants: list[str] | None, root: Path = ROOT) -> list[tuple[str, str, Path, dict]]:
    out = []
    for d in sorted(root.iterdir()):
        if not (d / "task.json").exists() or (tasks and d.name not in tasks):
            continue
        m = json.loads((d / "task.json").read_text())
        for v in m["variants"]:
            if variants and v not in variants:
                continue
            out.append((d.name, v, d / f"{v}.md", m))
    return out


def one(task: str, variant: str, skill: Path, m: dict, budget: float, rep: int) -> dict:
    ep = run_episode(skill, m["task"], max_budget_usd=budget, seed_files=m["seed_files"],
                     episode_id=f"{task}--{variant}--r{rep}-{time.strftime('%H%M%S')}")
    r = compute(ep)
    r["variant"] = variant
    r["rep"] = rep
    r["fault"] = m["variants"][variant].get("fault")
    r["fault_line"] = m["variants"][variant].get("line")
    r["success"] = check(ep / "work", m["check"])
    r["episode_dir"] = str(ep)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--tasks", nargs="*")
    ap.add_argument("--variants", nargs="*")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--budget", type=float, default=0.6)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--root", type=Path, default=ROOT)
    a = ap.parse_args()
    out = RUNS / "campaigns" / a.name
    out.mkdir(parents=True, exist_ok=True)
    res = out / "results.jsonl"
    done = set()
    if res.exists():
        for l in res.open():
            d = json.loads(l)
            done.add((d["skill_task"], d["variant"], d["rep"]))
    jobs = [(t, v, p, m, r) for (t, v, p, m) in list_skills(a.tasks, a.variants, a.root) for r in range(a.reps) if (t, v, r) not in done]
    print(f"{len(jobs)} épisodes à lancer ({len(done)} déjà faits)", flush=True)
    with ThreadPoolExecutor(a.parallel) as ex, res.open("a") as f:
        futs = {ex.submit(one, t, v, p, m, a.budget, r): (t, v, r) for (t, v, p, m, r) in jobs}
        for fut in as_completed(futs):
            t, v, r = futs[fut]
            try:
                d = fut.result()
            except Exception as e:  # on journalise l'échec du lanceur lui-même
                d = {"episode_id": None, "variant": v, "rep": r, "error": repr(e), "success": None}
            d["skill_task"] = t
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{t:14s} {v:20s} r{r} ok={d.get('success')} turns={d.get('num_turns')} tools={d.get('tool_calls')} ${d.get('cost_usd')}", flush=True)


if __name__ == "__main__":
    main()
