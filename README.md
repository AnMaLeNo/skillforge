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

## Résultats mesurés (campagne 1, 2026-10-25)

Corpus : 20 tâches × {base, proc, 2 défauts injectés à ligne connue} = 80 épisodes Sonnet 5.5 (~3,2 $ équivalent API).

- base / proc : 100 % de réussite ; l'agent obéit aux instructions nuisibles (s'arrêter pour demander 0/6,
  interdit de créer des fichiers 0/5, ne pas vérifier 6/6 obéi, travail en trop ×2 coût) et ignore les
  détails faux en le disant dans sa réponse finale (étape fausse 5/5, pandas imposé 6/6).
- Détection JEV (6 Noul, `detect.py`) : AUROC 0,87–0,99 selon la question ; une partie des « fausses alertes »
  sont des labels trop stricts (vérifié par signal code).
- Localisation (Choice sur lignes + « none ») : top-1 37/40, top-3 40/40, stable à la permutation 78/80 ;
  sur skills saines « none » n'est en tête que 29/40 → décider « problème ? » avant de localiser.
- Réécriture (`rewrite.py`, 20 skills, 2 axes, sélection JEV par paires en aveugle) : réussite 10/20 → 17/20,
  comportement signalé absent sur 20/20 relances ; axe « objectif + contexte » choisi 18/20.
  Les 3 échecs sont des contradictions internes résolues du mauvais côté : la pipeline localise la
  contradiction mais ne peut pas savoir seule quel nom de fichier est le vrai objectif.

Limites : tâches faciles (pas d'échec naturel), vérité terrain synthétique, un seul run par skill.
