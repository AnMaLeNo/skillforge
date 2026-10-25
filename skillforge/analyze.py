"""Tableaux de synthèse d'une campagne (code pur) et rendu d'un épisode pour l'étiquetage."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from .runner import RUNS
from .transcript import parse, render


def load(name: str) -> list[dict]:
    p = RUNS / "campaigns" / name / "results.jsonl"
    return [json.loads(l) for l in p.open()] if p.exists() else []


def table(rows: list[dict], key: str) -> str:
    g = defaultdict(list)
    for r in rows:
        g[str(r.get(key))].append(r)
    out = [f"{key:18s} {'n':>3s} {'réussite':>9s} {'tours':>6s} {'outils':>7s} {'err':>4s} {'répét':>6s} {'$moy':>7s}"]
    for k, rs in sorted(g.items()):
        n = len(rs)
        ok = sum(1 for r in rs if r.get("success"))
        avg = lambda f: sum((r.get(f) or 0) for r in rs) / n
        out.append(f"{k:18s} {n:3d} {ok/n:9.0%} {avg('num_turns'):6.1f} {avg('tool_calls'):7.1f} {avg('tool_errors'):4.1f} {avg('repeated_identical_calls'):6.1f} {avg('cost_usd'):7.3f}")
    return "\n".join(out)


def show(ep_dir: Path, max_chars: int = 1200) -> str:
    ep_dir = Path(ep_dir)
    meta = json.loads((ep_dir / "meta.json").read_text())
    skill = (ep_dir / "skill.md").read_text()
    steps = parse(ep_dir / "transcript.jsonl") if (ep_dir / "transcript.jsonl").exists() else []
    num = "\n".join(f"L{i+1}: {l}" for i, l in enumerate(skill.splitlines()))
    return f"=== {meta['episode_id']}\n--- SKILL\n{num}\n--- TRANSCRIPT\n{render(steps, max_chars_per_step=max_chars)}\n--- FICHIERS: {sorted(meta['files_after'])}\n"


if __name__ == "__main__":
    name = sys.argv[1]
    rows = load(name)
    print(f"{len(rows)} épisodes\n")
    print(table(rows, "variant"), "\n")
    print(table(rows, "fault"), "\n")
    if len(sys.argv) > 2 and sys.argv[2] == "--fails":
        for r in rows:
            if not r.get("success"):
                print(f"{r['skill_task']:14s} {r['variant']:22s} turns={r.get('num_turns')} tools={r.get('tool_calls')} err={r.get('tool_errors')} files={r.get('files_after')} | {(r.get('final_text') or '')[:160]!r}")
