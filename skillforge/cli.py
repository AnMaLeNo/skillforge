"""CLI : skillforge improve|answer|schema|replay."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import api, contract


def main(argv=None):
    ap = argparse.ArgumentParser(prog="skillforge")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("improve", help="skill(s) + trace → verdict JSON")
    p.add_argument("--skill", type=Path, action="append", required=True); p.add_argument("--trace", type=Path, required=True)
    p.add_argument("--report", type=Path, help="JSON {status, needs_human, summary} déclaré par l'agent")
    p.add_argument("--store", type=Path, default=Path(".skillforge")); p.add_argument("--llm", action="store_true", help="question rédigée par claude -p")
    p = sub.add_parser("answer", help="enregistre la réponse de l'auteur ; portée + patch éventuel")
    p.add_argument("--skill", type=Path, required=True); p.add_argument("--skill-id", required=True)
    p.add_argument("--question", required=True); p.add_argument("--answer", required=True)
    p.add_argument("--episode"); p.add_argument("--store", type=Path, default=Path(".skillforge"))
    p = sub.add_parser("episode", help="verdict depuis un Episode JSON (stdin ou fichier)")
    p.add_argument("file", nargs="?", type=Path); p.add_argument("--store", type=Path, default=Path(".skillforge")); p.add_argument("--llm", action="store_true")
    sub.add_parser("schema", help="JSON schemas du contrat")
    a = ap.parse_args(argv)
    if a.cmd == "schema":
        print(json.dumps(contract.schemas(), indent=1, ensure_ascii=False)); return
    if a.cmd == "improve":
        rep = json.loads(a.report.read_text()) if a.report else None
        ep = api.episode_from_files(a.skill, a.trace, report=rep)
        print(api.improve(ep, store=a.store, draft_with_llm=a.llm).model_dump_json(indent=1)); return
    if a.cmd == "episode":
        ep = contract.Episode.model_validate_json(a.file.read_text() if a.file else sys.stdin.read())
        print(api.improve(ep, store=a.store, draft_with_llm=a.llm).model_dump_json(indent=1)); return
    if a.cmd == "answer":
        r = api.answer(contract.Answer(skill_id=a.skill_id, question=a.question, answer=a.answer, episode_id=a.episode),
                       store=a.store, skill_text=a.skill.read_text())
        print(r.model_dump_json(indent=1))


if __name__ == "__main__":
    main()
