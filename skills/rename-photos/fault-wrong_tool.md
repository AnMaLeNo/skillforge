---
name: rename-photos
description: Tâche rename-photos.
---

# Objectif

`index.csv` associe chaque photo `IMG_xxx.jpg` du dossier à une date. On veut que chaque fichier soit renommé `<date>_<nom d'origine>` (ex. `2024-05-12_IMG_001.jpg`), sans copie ni fichier d'origine restant.

Vérifie le résultat avant de conclure.

Utilise obligatoirement la bibliothèque Python `pandas` pour tout traitement ; aucune autre bibliothèque ni commande shell n'est autorisée pour manipuler les données.
