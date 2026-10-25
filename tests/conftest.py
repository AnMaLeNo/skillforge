import json
from pathlib import Path

import pytest

from skillforge.contract import AgentReport, Episode, SkillRef, Trace

FIX = Path(__file__).parent / "fixtures" / "infra"
SKILLS = Path.home() / "repos" / "infra" / "skills"  # skills du client infra (clone local) ; sinon texte minimal


def skill_text(name: str) -> str:
    p = SKILLS / name / "SKILL.md"
    return p.read_text() if p.exists() else f"---\nname: {name}\n---\n## But\n(skill {name} indisponible dans ce test)\n"


def infra_episode(run_json: Path) -> Episode:
    rec = json.loads(run_json.read_text())
    return Episode(id=run_json.stem, skills=[SkillRef(id=s, text=skill_text(s)) for s in rec["skills"]],
                   trace=Trace(format="claude-stream-json", path=str(run_json.with_suffix(".log"))),
                   agent_report=AgentReport(status=rec.get("status"), needs_human=rec.get("needs_human"), summary=rec.get("report")),
                   meta={"project": rec.get("project"), "declared_ok": rec.get("ok")})


@pytest.fixture(scope="session")
def infra_episodes() -> list[Episode]:
    return [infra_episode(p) for p in sorted(FIX.glob("*.json"))]
