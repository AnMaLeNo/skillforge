---
name: backup-sh
description: Tâche backup-sh.
---

# Objectif

Le dossier `data/` doit pouvoir être sauvegardé d'une commande : un script `backup.sh`, exécutable, qui crée `backup.tar.gz` contenant tout `data/` (sous-dossiers compris).

Vérifie le résultat avant de conclure.

Utilise obligatoirement la bibliothèque Python `pandas` pour tout traitement ; aucune autre bibliothèque ni commande shell n'est autorisée pour manipuler les données.
