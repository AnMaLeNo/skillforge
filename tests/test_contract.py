import json

from skillforge import contract
from skillforge.api import _combined, _passage, _steps


def test_schemas_export():
    s = contract.schemas()
    assert set(s) == {"Episode", "Verdict", "Answer", "AnswerResult"}
    assert "decision" in s["Verdict"]["properties"]
    json.dumps(s)


def test_episode_roundtrip(infra_episodes):
    ep = infra_episodes[0]
    again = contract.Episode.model_validate_json(ep.model_dump_json())
    assert again == ep and again.version == contract.VERSION


def test_fixtures_parse_offline(infra_episodes):
    assert len(infra_episodes) == 10
    for ep in infra_episodes:
        steps = _steps(ep)
        assert any(s.kind == "tool_use" for s in steps) and any(s.kind == "assistant" for s in steps)


def test_passage_maps_back_to_skill(infra_episodes):
    ep = next(e for e in infra_episodes if len(e.skills) >= 2)
    text, table = _combined(ep)
    lines = text.splitlines()
    n1 = len(ep.skills[0].text.splitlines())
    g = n1 + 4  # en-tête skill1 + n1 lignes + en-tête skill2 + 2e ligne
    p = _passage(f"L{g}", lines[g - 1], table)
    assert p.skill_id == ep.skills[1].id and p.line == 2 and p.text == ep.skills[1].text.splitlines()[1]


def test_indisponible_on_bad_trace(tmp_path):
    from skillforge import api
    ep = contract.Episode(id="x", skills=[contract.SkillRef(id="s", text="## But\nfaire")], trace=contract.Trace(path=str(tmp_path / "absent.log")))
    v = api.improve(ep, store=tmp_path / "store")
    assert v.decision == "indisponible" and v.errors
