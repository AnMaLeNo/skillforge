"""Corpus « dur » : tâches à pièges (cas limites réels) pour provoquer des échecs
naturels. Seulement base (objectif) et proc (procédure), pas de défaut injecté.
Les valeurs attendues sont calculées ici par une implémentation de référence."""
from __future__ import annotations

import datetime as dt
import json
import random
from pathlib import Path

from .corpus import TASK_SENTENCE, _skill

ROOT = Path(__file__).resolve().parent.parent / "skills_hard"
rng = random.Random(7)


def _tasks() -> list[dict]:
    T = []
    # 1 csv-messy : BOM, guillemets avec virgules, décimales à virgule, espaces fines, négatifs entre parenthèses, lignes vides
    vals = [1234.56, -45.3, 7.0, 99.99, -1000.0, 12.5, 3.25, 850.1]
    body = ["\ufeffid;label;amount", '1;"Dupont, Jean";1 234,56', "", "2;Martin;(45,30)", "3;Durand;7", '4;"O\'Neil";99,99',
            "5;Petit;(1 000,00)", "6;Roux;12,5", "", "7;Blanc;3,25", "8;Noir;850,10"]
    T.append(dict(name="csv-messy", out="total.txt",
        seed={"ventes.csv": "\n".join(body) + "\n"},
        objective="`ventes.csv` est un export comptable français (séparateur `;`, décimales à virgule, espaces de milliers, montants négatifs entre parenthèses, lignes vides, BOM possible). Il faut la somme exacte de la colonne `amount`, écrite avec 2 décimales seule sur la première ligne de `{out}`.",
        steps=["Ouvre `ventes.csv` avec `csv.reader`, délimiteur `;`.", "Convertis chaque `amount` en float après avoir retiré les espaces et remplacé la virgule par un point.", "Additionne et écris le total avec 2 décimales dans `{out}`."],
        check=f"python3 -c \"import sys; v=float(open('total.txt').read().split()[0]); sys.exit(0 if abs(v-{round(sum(vals),2)})<0.005 else 1)\""))
    # 2 iso-weeks : compter des événements par semaine ISO (année ISO), bornes d'année + bissextile
    dates = ["2024-12-30", "2024-12-31", "2025-01-01", "2025-01-05", "2025-01-06", "2024-02-29", "2024-03-01", "2021-01-03", "2021-01-04", "2020-12-31", "2026-01-01", "2026-01-04"]
    exp = {}
    for d in dates:
        y, w, _ = dt.date.fromisoformat(d).isocalendar()
        k = f"{y}-W{w:02d}"; exp[k] = exp.get(k, 0) + 1
    T.append(dict(name="iso-weeks", out="weeks.json",
        seed={"events.txt": "\n".join(dates) + "\n"},
        objective="`events.txt` contient une date ISO par ligne. On veut `{out}` : un objet JSON `{{\"AAAA-Www\": nombre}}` qui compte les événements par semaine ISO 8601 (l'année est l'année ISO de la semaine, pas l'année civile).",
        steps=["Lis les dates avec `datetime.date.fromisoformat`.", "Pour chaque date, calcule la clé `AAAA-Www` à partir de `isocalendar()`.", "Compte et écris le JSON dans `{out}`."],
        check=f"python3 -c \"import json,sys; sys.exit(0 if json.load(open('weeks.json'))=={exp!r} else 1)\""))
    # 3 interval-merge : fusion d'intervalles (non triés, inclus, adjacents à fusionner)
    iv = [(5, 8), (1, 3), (2, 6), (10, 12), (12, 15), (20, 21), (14, 14), (30, 35), (31, 32)]
    s = sorted(iv); merged = []
    for a, b in s:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    T.append(dict(name="interval-merge", out="merged.txt",
        seed={"intervals.txt": "\n".join(f"{a} {b}" for a, b in iv) + "\n"},
        objective="`intervals.txt` contient un intervalle entier fermé `a b` par ligne, dans le désordre. On veut `{out}` : les intervalles fusionnés (deux intervalles qui se chevauchent ou se touchent n'en font qu'un), un par ligne `a b`, triés par début.",
        steps=["Lis les paires d'entiers.", "Trie par début.", "Parcours en fusionnant quand `a <= fin courante`.", "Écris le résultat dans `{out}`."],
        check=f"python3 -c \"import sys; got=[tuple(map(int,l.split())) for l in open('merged.txt') if l.strip()]; sys.exit(0 if got=={[tuple(m) for m in merged]!r} else 1)\""))
    # 4 roman : conversion aller-retour avec validation stricte
    cases = {"MCMXCIV": 1994, "XLII": 42, "MMXXIV": 2024, "IV": 4, "XC": 90, "CDXLIV": 444, "MMMCMXCIX": 3999}
    bad = ["IIII", "VX", "IC", "MMMM", "", "abc", "IXI"]
    T.append(dict(name="roman", out="roman.py",
        seed={"README.txt": "Module attendu : roman.py avec to_roman(int)->str et from_roman(str)->int.\n"},
        objective="On a besoin d'un module `{out}` exposant `to_roman(n)` (1..3999) et `from_roman(s)`. `from_roman` doit lever `ValueError` pour toute chaîne qui n'est pas un numéral romain canonique (ex. `IIII`, `VX`, `IC`, `MMMM`, chaîne vide), et `to_roman(from_roman(s)) == s` pour tout numéral valide.",
        steps=["Écris `to_roman` avec la table des 13 symboles (M, CM, D, CD, C, XC, L, XL, X, IX, V, IV, I).", "Écris `from_roman` qui additionne les valeurs avec la règle de soustraction.", "Ajoute la validation : `from_roman` lève `ValueError` si `to_roman(valeur) != s`.", "Teste sur quelques exemples."],
        check=f"python3 -c \"import sys,roman; ok=all(roman.to_roman(v)==k and roman.from_roman(k)==v for k,v in {cases!r}.items())\nfor b in {bad!r}:\n    try: roman.from_roman(b); ok=False\n    except ValueError: pass\n    except Exception: ok=False\nsys.exit(0 if ok else 1)\""))
    # 5 log-dedupe : erreurs par service, en ignorant les répétitions du même message dans la même seconde, traces multi-lignes
    lines = ["2025-03-01T10:00:00Z api ERROR timeout on /users", "2025-03-01T10:00:00Z api ERROR timeout on /users", "2025-03-01T10:00:01Z api ERROR timeout on /users",
             "2025-03-01T10:00:02Z db ERROR connection refused", "Traceback (most recent call last):", "  File x.py, line 1", "psycopg.OperationalError: refused",
             "2025-03-01T10:00:03Z api INFO ok", "2025-03-01T10:00:03Z worker ERROR job failed", "2025-03-01T10:00:03Z worker ERROR job failed", "2025-03-01T10:00:04Z worker ERROR job failed", "2025-03-01T10:00:04Z api WARN slow"]
    exp5 = {"api": 2, "db": 1, "worker": 2}
    T.append(dict(name="log-dedupe", out="errors.json",
        seed={"app.log": "\n".join(lines) + "\n"},
        objective="`app.log` mélange des lignes `horodatage service NIVEAU message` et des traces Python multi-lignes (sans horodatage). On veut `{out}` : un JSON `{{service: nombre d'erreurs}}` où une même erreur (même service, même message) répétée dans la même seconde ne compte qu'une fois.",
        steps=["Ne garde que les lignes qui commencent par un horodatage ISO et dont le niveau est ERROR.", "Dédoublonne sur (horodatage à la seconde, service, message).", "Compte par service et écris `{out}`."],
        check=f"python3 -c \"import json,sys; sys.exit(0 if json.load(open('errors.json'))=={exp5!r} else 1)\""))
    # 6 fix-bugs : deux bugs dans un module (off-by-one + mutable default), tests cachés
    T.append(dict(name="fix-bugs", out="stats.py",
        seed={"stats.py": "def moving_avg(xs, k):\n    out = []\n    for i in range(len(xs) - k):\n        out.append(sum(xs[i:i+k]) / k)\n    return out\n\n\ndef collect(x, acc=[]):\n    acc.append(x)\n    return acc\n\n\ndef median(xs):\n    s = sorted(xs)\n    n = len(s)\n    return s[n // 2]\n",
              "test_stats.py": "from stats import moving_avg, collect, median\nassert moving_avg([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5]\nassert collect(1) == [1] and collect(2) == [2]\nassert median([3, 1, 2]) == 2 and median([4, 1, 3, 2]) == 2.5\nprint('OK')\n"},
        objective="`python3 test_stats.py` échoue. Le module `{out}` doit être corrigé pour que ses trois fonctions fassent ce que leur nom indique (moyenne glissante complète, `collect` sans état partagé entre appels, médiane correcte pour un nombre pair d'éléments), sans modifier le test.",
        steps=["Lance `python3 test_stats.py` et lis la première erreur.", "Corrige la fonction concernée dans `{out}`.", "Relance jusqu'à `OK`."],
        check="python3 test_stats.py && python3 -c \"from stats import collect, median, moving_avg; assert collect(5)==[5]; assert median([1,2])==1.5; assert moving_avg([1,2,3],3)==[2.0]\""))
    # 7 name-dedupe : dédoublonnage de contacts (casse, accents, espaces, e-mail normalisé)
    contacts = ["Élodie Martin <Elodie.Martin@Example.com>", "elodie martin <elodie.martin@example.com>", "Jean  Dupont <jean.dupont@example.com>", "Jean Dupont <JEAN.DUPONT@example.com >",
                "Zoé Durand <zoe.durand@example.com>", "Zoe Durand <zoe.durand@example.com>", "Marc Petit <marc.petit@example.com>", "Marc Petit <marc.petit@sample.com>"]
    T.append(dict(name="name-dedupe", out="unique.txt",
        seed={"contacts.txt": "\n".join(contacts) + "\n"},
        objective="`contacts.txt` contient des contacts `Nom <email>` saisis à la main (casse, accents, espaces multiples, espaces autour de l'e-mail variables). Deux lignes désignent la même personne si leurs e-mails normalisés (minuscules, espaces retirés) sont égaux. On veut `{out}` : une ligne par personne, la première occurrence rencontrée, dans l'ordre d'apparition.",
        steps=["Extrais l'e-mail entre `<` et `>`.", "Normalise-le en minuscules sans espaces.", "Garde la première ligne par e-mail normalisé et écris `{out}`."],
        check="python3 -c \"import sys; got=[l.rstrip('\\n') for l in open('unique.txt') if l.strip()]; exp=['Élodie Martin <Elodie.Martin@Example.com>','Jean  Dupont <jean.dupont@example.com>','Zoé Durand <zoe.durand@example.com>','Marc Petit <marc.petit@example.com>','Marc Petit <marc.petit@sample.com>']; sys.exit(0 if got==exp else 1)\""))
    # 8 todo-cli : CLI persistante avec codes de sortie
    T.append(dict(name="todo-cli-strict", out="todo.py",
        seed={"README.txt": "CLI attendue : python3 todo.py add TEXTE | done ID | list\n"},
        objective="On a besoin d'un outil en ligne de commande `{out}` : `add TEXTE` affiche l'ID attribué (entiers croissants à partir de 1), `done ID` marque la tâche faite et renvoie le code de sortie 1 avec un message sur stderr si l'ID n'existe pas, `list` affiche une ligne `ID [x] texte` ou `ID [ ] texte` par tâche. L'état doit survivre entre deux exécutions (fichier dans le dossier courant). Un sous-commande inconnue renvoie le code 2.",
        steps=["Utilise `argparse` avec sous-commandes `add`, `done`, `list`.", "Stocke les tâches dans `todo.json`.", "Implémente les codes de sortie 1 (ID inconnu) et 2 (commande inconnue).", "Teste la séquence add/add/done/list."],
        check="python3 todo.py add 'a' >/dev/null && python3 todo.py add 'b' >/dev/null && python3 todo.py done 2 >/dev/null && python3 todo.py list | grep -q '^2 \\[x\\] b' && python3 todo.py list | grep -q '^1 \\[ \\] a' && ! python3 todo.py done 9 2>/dev/null; [ $? -eq 0 ] && python3 todo.py done 9 2>/dev/null; [ $? -eq 1 ] && python3 todo.py frob >/dev/null 2>&1; [ $? -eq 2 ]"))
    return T


def build(root: Path = ROOT) -> dict:
    manifest = {}
    for t in _tasks():
        d = root / t["name"]
        d.mkdir(parents=True, exist_ok=True)
        out = t["out"]
        base = ["# Objectif", "", t["objective"].format(out=out), "", "Vérifie le résultat avant de conclure."]
        proc = ["# Procédure", "", *[f"{i+1}. {s.format(out=out)}" for i, s in enumerate(t["steps"])]]
        (d / "base.md").write_text(_skill(t["name"], base))
        (d / "proc.md").write_text(_skill(t["name"], proc))
        manifest[t["name"]] = {"task": TASK_SENTENCE, "out": out, "seed_files": t["seed"], "check": t["check"],
                               "variants": {"base": {"fault": None}, "proc": {"fault": None}}}
        (d / "task.json").write_text(json.dumps(manifest[t["name"]], indent=1, ensure_ascii=False))
    return manifest


if __name__ == "__main__":
    m = build()
    print(f"{len(m)} tâches dures, {sum(len(v['variants']) for v in m.values())} skills → {ROOT}")
