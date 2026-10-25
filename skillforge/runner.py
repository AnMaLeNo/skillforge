"""Lance un épisode : un agent Claude Code (claude -p) qui ne reçoit que la skill
(ajoutée au system prompt) et une phrase de tâche, dans un dossier sandbox vide.
Sauvegarde le transcript JSONL brut, la sortie JSON de claude -p et l'état final
des fichiers, pour que tout soit vérifiable après coup.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

MODEL = "claude-sonnet-5-5"
RUNS = Path(os.environ.get("SKILLFORGE_RUNS", Path(__file__).resolve().parent.parent / "runs"))
CONFIG_DIR = Path(os.environ.get("SKILLFORGE_CLAUDE_CONFIG", Path.home() / ".claude-skillforge"))


def _snapshot(d: Path) -> dict:
    out = {}
    for p in sorted(d.rglob("*")):
        if p.is_file() and ".git/" not in str(p):
            rel = str(p.relative_to(d))
            b = p.read_bytes()
            out[rel] = {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()[:16]}
    return out


def _find_transcript(session_id: str) -> Path | None:
    hits = list((CONFIG_DIR / "projects").rglob(f"{session_id}.jsonl"))
    return hits[0] if hits else None


def run_episode(skill_path: Path, task: str, *, episode_id: str | None = None,
                model: str = MODEL, max_budget_usd: float = 0.6,
                timeout_s: int = 900, seed_files: dict[str, str] | None = None) -> Path:
    """Retourne le dossier de l'épisode (meta.json, transcript.jsonl, work/)."""
    skill_path = Path(skill_path)
    stem = skill_path.parent.name + "-" + skill_path.stem if skill_path.stem.upper() == "SKILL" else skill_path.parent.name + "-" + skill_path.stem
    episode_id = episode_id or f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    ep = RUNS / "episodes" / episode_id
    work = ep / "work"
    work.mkdir(parents=True, exist_ok=False)
    for rel, content in (seed_files or {}).items():
        p = work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    shutil.copy(skill_path, ep / "skill.md")
    session_id = str(uuid.uuid4())
    cmd = ["claude", "-p", task, "--model", model, "--output-format", "json",
           "--dangerously-skip-permissions", "--max-budget-usd", str(max_budget_usd),
           "--session-id", session_id,
           "--append-system-prompt", skill_path.read_text(),
           "--setting-sources", ""]
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = str(CONFIG_DIR)
    env.pop("ANTHROPIC_BASE_URL", None)  # jamais via OpenRouter pour le LLM
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    env.pop("ANTHROPIC_API_KEY", None)
    CONFIG_DIR.mkdir(exist_ok=True)
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, timeout=timeout_s)
        timed_out = False
        stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        timed_out = True
        stdout = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = (e.stderr or b"").decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        rc = -1
    wall_ms = int((time.time() - t0) * 1000)
    result = None
    try:
        result = json.loads(stdout) if stdout.strip() else None
    except json.JSONDecodeError:
        pass
    (ep / "stdout.json").write_text(stdout)
    if stderr:
        (ep / "stderr.txt").write_text(stderr)
    tpath = _find_transcript(session_id)
    if tpath:
        shutil.copy(tpath, ep / "transcript.jsonl")
    meta = {
        "episode_id": episode_id, "skill": skill_path.name, "task": task, "model": model,
        "session_id": session_id, "cmd": [c if len(c) < 200 else "<skill>" for c in cmd], "rc": rc, "timed_out": timed_out, "wall_ms": wall_ms,
        "transcript": bool(tpath),
        "claude": {k: result.get(k) for k in ("subtype", "is_error", "duration_ms", "duration_api_ms",
                                               "num_turns", "total_cost_usd", "stop_reason")} if result else None,
        "result_text": (result or {}).get("result"),
        "files_after": _snapshot(work),
    }
    (ep / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    return ep


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("skill")
    ap.add_argument("task")
    ap.add_argument("--budget", type=float, default=0.6)
    a = ap.parse_args()
    ep = run_episode(Path(a.skill), a.task, max_budget_usd=a.budget)
    print(ep)
    print(json.dumps(json.loads((ep / "meta.json").read_text())["claude"], indent=1))
