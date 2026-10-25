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

## Décision « rien / reformuler / demander » et question à l'auteur (ajout du 25/10)

Principe (fixé par l'utilisateur) : quand l'information manque dans la skill, on ne l'invente pas, on la demande à l'auteur.
`skillforge/decide.py` mesure la règle de décision sur 106 cas étiquetés (61 rien, 34 reformuler, 11 demander : défauts
injectés c1, corpus dur, runs réels du projet infra). Traits = 6 comportements + 3 questions contexte JEV
(`missing_context`, `ambiguous`, `blocked_by_env`). Seuils calibrés sur une moitié des tâches, mesurés sur l'autre
(deux découpages) : **exactitude équilibrée 0,80** sur held-out dans les deux sens ; rapport dans `docs/decide-report-2026-10-25.txt`.

`python -m skillforge.improve SKILL.md TRACE [--report run.json]` enchaîne tout : JEV → décision → `rien`, `reformuler`
(passage + preuves) ou `demander` (paquet auteur : passage, pourquoi, extraits bruts, question). `improve.draft_question`
fait rédiger la question par Sonnet (sans outil, ~0,01 $) puis JEV vérifie « n'invente aucun fait » et « répondable en une
phrase » ; sinon retour à la question générique assemblée par code. Sur 9 cas réels : 8 acceptées, 1 rejetée à tort.

`skillforge/ambiguity.py` : historique Q/R **par skill** (`runs/qa_history.jsonl`), `already_answered` (JEV retrouve une
réponse déjà donnée : 0,72 sur le cas réel, « aucune » ≥ 0,89 sur 5 autres besoins), `scope_of` (réponse ponctuelle vs
règle générale à intégrer à la skill : 0,07 vs 0,79 sur le même contenu reformulé).

Non prouvé : la boucle fermée réponse → skill → relance sans blocage (attend un prochain blocage réel).

## Contrat et API (brique générique, v1)

skillforge ne connaît aucun client : il reçoit un **Episode** (skills utilisées, trace brute Claude Code — session `.jsonl`
ou stream-json —, rapport déclaré par l'agent s'il existe, vérification s'il y en a une) et rend un **Verdict**
(`rien | reformuler | demander | indisponible`, scores, passage de skill, extraits bruts, question, réponse d'historique,
patch proposé en diff, coût). Modèles pydantic dans `skillforge/contract.py`, schémas via `skillforge schema`.

```bash
pip install git+https://github.com/AnMaLeNo/skillforge
skillforge improve --skill SKILL.md --trace session.jsonl [--report report.json] [--store .skillforge] [--llm]
skillforge answer  --skill SKILL.md --skill-id expose/public --question "…" --answer "…"   # portée + patch si générale
skillforge episode episode.json                                                           # depuis un Episode JSON
```

API : `skillforge.api.improve(episode, store=…) -> Verdict`, `answer(Answer, store=…, skill_text=…) -> AnswerResult`,
`replay([...])`. Tout l'état (historique Q/R, journal et cache JEV) est dans `store`, fourni par le client ; skillforge
n'applique jamais un patch lui-même. `indisponible` (JEV absent, trace illisible…) est une sortie normale : le client
ne doit pas échouer à cause de skillforge.

Tests : `tests/fixtures/infra/` = 10 runs réels du client infra (secrets masqués) ; `pytest tests/test_contract.py`
(hors ligne) ; `pytest tests/test_replay.py` (JEV, ~0,01 $) vérifie que les 5 runs bloqués donnent `demander` et les
5 autres non, et fige les verdicts dans `tests/fixtures/infra-verdicts.json`.
