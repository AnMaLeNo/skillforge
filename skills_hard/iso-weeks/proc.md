---
name: iso-weeks
description: Tâche iso-weeks.
---

# Procédure

1. Lis les dates avec `datetime.date.fromisoformat`.
2. Pour chaque date, calcule la clé `AAAA-Www` à partir de `isocalendar()`.
3. Compte et écris le JSON dans `weeks.json`.
