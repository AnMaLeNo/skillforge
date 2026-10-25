---
name: name-dedupe
description: Tâche name-dedupe.
---

# Objectif

`contacts.txt` contient des contacts `Nom <email>` saisis à la main (casse, accents, espaces multiples, espaces autour de l'e-mail variables). Deux lignes désignent la même personne si leurs e-mails normalisés (minuscules, espaces retirés) sont égaux. On veut `unique.txt` : une ligne par personne, la première occurrence rencontrée, dans l'ordre d'apparition.

Vérifie le résultat avant de conclure.
