---
name: sqlite-report
description: Tâche sqlite-report.
---

# Procédure

1. Importe `sales.csv` dans `sales.db`, table `sales`, avec le module `sqlite3`.
2. Requête `SELECT region, SUM(amount) GROUP BY region`.
3. Écris `report.txt`.
4. Affiche-le.
