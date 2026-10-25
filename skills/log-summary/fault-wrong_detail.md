---
name: log-summary
description: Tâche log-summary.
---

# Procédure

1. Récupère le premier champ de chaque ligne (le niveau).
2. Récupère le deuxième champ de chaque ligne.
3. Compte par niveau avec `collections.Counter`.
4. Écris `summary.json`.
