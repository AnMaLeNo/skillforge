# skillforge

Système pour créer et améliorer des skills (fichiers d'instructions type `SKILL.md`)
à partir des transcripts d'agents qui les utilisent. Décisions structurées par JEV
(TypeSafe, `typesafe/jev-1.13` via OpenRouter Decisions API) ; réécriture par
`claude -p --model claude-sonnet-5-5` ; mesures exactes et contrôle de flux en code.

## Principe

- Le code découpe, compte, sélectionne ; JEV ne répond qu'à des questions atomiques
  (Noul / Choice / Score) sur un état minimal ; le code agrège.
- Chaque appel JEV est journalisé (`runs/jev_log.jsonl`) et mis en cache.
- Un épisode = un agent Claude Code lancé seul dans un dossier sandbox avec la skill
  en system prompt et une phrase de tâche ; transcript JSONL brut conservé.
- Le succès d'une tâche est décidé par une commande de vérification, pas par un LLM.

## Modules

- `skillforge/jev.py` — client JEV (journal, cache, garde 32k tokens).
- `skillforge/runner.py` — lance un épisode `claude -p`, sauvegarde transcript + méta + état des fichiers.
- `skillforge/transcript.py` — parseur JSONL → étapes plates.
- `skillforge/metrics.py` — signaux exacts (répétitions, erreurs, tokens, « terminé » sans vérification…).
- `skillforge/corpus.py` — 20 tâches × 4 skills (objectif / procédure / 2 défauts injectés à ligne connue).
- `skillforge/campaign.py` — lance un lot d'épisodes, vérifie, écrit `runs/campaigns/<nom>/results.jsonl`.

## Usage

```bash
export OPENROUTER_API_KEY=…          # JEV uniquement
export CLAUDE_CODE_OAUTH_TOKEN=…     # claude setup-token
python3 -m skillforge.corpus          # génère skills/
python3 -m skillforge.campaign c1 --parallel 4
```
