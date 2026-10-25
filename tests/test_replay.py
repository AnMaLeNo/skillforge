"""Replay des 10 runs réels (appels JEV : OPENROUTER_API_KEY requis, ~0,01 $ ; réponses mises en cache dans le store)."""
import json
import os
from pathlib import Path

import pytest

from skillforge import api, contract

pytestmark = pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="JEV indisponible")
GOLDEN = Path(__file__).parent / "fixtures" / "infra-verdicts.json"


def test_replay_matches_offline_analysis(infra_episodes, tmp_path):
    store = Path(os.environ.get("SKILLFORGE_TEST_STORE", tmp_path / "store"))
    verdicts = api.replay(infra_episodes, store=store)
    got = {v.episode_id: v.decision for v in verdicts}
    blocked = {e.id for e in infra_episodes if e.agent_report and e.agent_report.status in ("bloqué", None)}
    assert all(got[i] == "demander" for i in blocked), got
    assert all(got[i] != "demander" for i in got if i not in blocked), got
    assert all(v.decision != "indisponible" for v in verdicts)
    assert sum(v.cost.jev_usd for v in verdicts) < 0.05
    if GOLDEN.exists():
        assert got == json.loads(GOLDEN.read_text())
    else:
        GOLDEN.write_text(json.dumps(got, indent=1, ensure_ascii=False))


def test_answer_general_gives_patch(tmp_path):
    skill = "---\nname: expose/public\n---\n## Pièges connus\n- `dns_ensure` renvoie `conflict` : ne force que si tu es sûr ; sinon demande.\n"
    r = api.answer(contract.Answer(skill_id="expose/public", question="Forcer la bascule DNS ?",
                                   answer="Quand le registre indique en `legacy:` que l'ancien chemin d'exposition doit être abandonné, `dns_ensure(force=True)` est autorisé sans redemander ; sinon, demander."),
                   store=tmp_path / "store", skill_text=skill)
    assert r.scope == "general" and r.proposed_patch and "Précisions de l'auteur" in r.proposed_patch.diff
    r2 = api.answer(contract.Answer(skill_id="expose/public", question="Forcer la bascule DNS ?",
                                    answer="BASCULE AUTORISÉE pour catacombes le 2026-10-22 : dns_ensure(force=True)."),
                    store=tmp_path / "store", skill_text=skill)
    assert r2.scope == "ponctuel" and r2.proposed_patch is None
