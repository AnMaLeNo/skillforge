"""Contrat d'interface de skillforge (v1) : ce qu'un client fournit (Episode) et ce qu'il reçoit (Verdict).
Aucune référence à un client particulier. `python -m skillforge.cli schema` exporte les JSON schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

VERSION = "1"
Decision = Literal["rien", "reformuler", "demander", "indisponible"]


class SkillRef(BaseModel):
    id: str = Field(description="Identifiant stable de la skill chez le client (ex. chemin `expose/public`).")
    text: str = Field(description="Contenu intégral du SKILL.md tel que donné à l'agent.")


class Trace(BaseModel):
    format: Literal["claude-stream-json", "claude-session-jsonl"] = "claude-stream-json"
    path: str | None = Field(default=None, description="Fichier, une ligne JSON par événement.")
    events: list[dict] | None = Field(default=None, description="Ou les événements déjà chargés.")


class AgentReport(BaseModel):
    """Ce que l'agent a déclaré lui-même en fin de run (donnée brute, pas un jugement)."""
    status: str | None = None
    needs_human: str | None = None
    summary: str | None = None


class Verification(BaseModel):
    ok: bool
    cmd: str | None = None


class Episode(BaseModel):
    version: str = VERSION
    id: str
    skills: list[SkillRef]
    trace: Trace
    agent_report: AgentReport | None = None
    verification: Verification | None = None
    meta: dict = Field(default_factory=dict, description="Libre : modèle, coût, tours, durée, projet…")


class Passage(BaseModel):
    skill_id: str
    line: int = Field(description="Numéro de ligne (1-based) dans le texte de la skill.")
    text: str


class Evidence(BaseModel):
    step: int
    kind: str
    text: str


class Question(BaseModel):
    text: str
    fact: str | None = None
    source: Literal["code", "llm"] = "code"
    checks: dict[str, float] = Field(default_factory=dict, description="Contrôles JEV sur la question rédigée (invente, repondable).")


class HistoryHit(BaseModel):
    question: str
    answer: str
    scope: str | None = None
    probability: float


class Patch(BaseModel):
    skill_id: str
    diff: str = Field(description="Diff unifié du SKILL.md ; à valider par un humain, jamais appliqué par skillforge.")


class Cost(BaseModel):
    jev_usd: float = 0.0
    claude_usd: float = 0.0


class Verdict(BaseModel):
    version: str = VERSION
    episode_id: str
    decision: Decision
    scores: dict[str, float] = Field(default_factory=dict)
    why: list[str] = Field(default_factory=list)
    passage: Passage | None = None
    behaviours: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    question: Question | None = None
    history_hit: HistoryHit | None = None
    proposed_patch: Patch | None = None
    cost: Cost = Field(default_factory=Cost)
    errors: list[str] = Field(default_factory=list)


class Answer(BaseModel):
    """Réponse de l'auteur à une question ; `scope` est décidé par skillforge si absent."""
    skill_id: str
    question: str
    answer: str
    episode_id: str | None = None
    scope: Literal["general", "ponctuel"] | None = None


class AnswerResult(BaseModel):
    scope: Literal["general", "ponctuel"]
    general_probability: float
    contradicts_skill: float
    proposed_patch: Patch | None = None


def schemas() -> dict:
    return {name: m.model_json_schema() for name, m in (("Episode", Episode), ("Verdict", Verdict), ("Answer", Answer), ("AnswerResult", AnswerResult))}
