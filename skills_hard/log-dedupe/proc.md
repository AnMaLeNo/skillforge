---
name: log-dedupe
description: Tâche log-dedupe.
---

# Procédure

1. Ne garde que les lignes qui commencent par un horodatage ISO et dont le niveau est ERROR.
2. Dédoublonne sur (horodatage à la seconde, service, message).
3. Compte par service et écris `errors.json`.
