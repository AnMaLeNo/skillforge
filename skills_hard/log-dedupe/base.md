---
name: log-dedupe
description: Tâche log-dedupe.
---

# Objectif

`app.log` mélange des lignes `horodatage service NIVEAU message` et des traces Python multi-lignes (sans horodatage). On veut `errors.json` : un JSON `{service: nombre d'erreurs}` où une même erreur (même service, même message) répétée dans la même seconde ne compte qu'une fois.

Vérifie le résultat avant de conclure.
