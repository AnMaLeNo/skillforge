---
name: todo-cli-strict
description: Tâche todo-cli-strict.
---

# Objectif

On a besoin d'un outil en ligne de commande `todo.py` : `add TEXTE` affiche l'ID attribué (entiers croissants à partir de 1), `done ID` marque la tâche faite et renvoie le code de sortie 1 avec un message sur stderr si l'ID n'existe pas, `list` affiche une ligne `ID [x] texte` ou `ID [ ] texte` par tâche. L'état doit survivre entre deux exécutions (fichier dans le dossier courant). Un sous-commande inconnue renvoie le code 2.

Vérifie le résultat avant de conclure.
