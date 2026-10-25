"""Corpus de skills synthétiques : 20 tâches courtes, vérifiables par code.

Pour chaque tâche : une skill « objectif » (base), une skill « procédure » (proc)
et deux skills avec un défaut injecté dont on connaît la ligne exacte (vérité
terrain pour la localisation). Génère skills/<tâche>/{base,proc,fault-*}.md +
task.json (phrase de tâche, fichiers seed, commande de vérification, défauts).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "skills"
TASK_SENTENCE = "Fais la tâche décrite dans la skill, dans le dossier courant."

# Défauts génériques : (type, ligne à ajouter en fin de skill). {out} = fichier de sortie, {alt} = autre nom.
GENERIC_FAULTS = {
    "no_verify": "Ne lance aucune commande pour vérifier ou tester le résultat : écris ce qu'il faut et conclus directement.",
    "ask_user": "Avant de commencer, demande à l'utilisateur de confirmer le nom exact du fichier de sortie et attends sa réponse.",
    "overreach": "Produis aussi une documentation complète (README détaillé, docstrings partout, au moins 30 tests unitaires et un CHANGELOG) avant de considérer la tâche terminée.",
    "wrong_tool": "Utilise obligatoirement la bibliothèque Python `pandas` pour tout traitement ; aucune autre bibliothèque ni commande shell n'est autorisée pour manipuler les données.",
    "contradiction": "Le résultat final doit impérativement être écrit dans `{alt}`.",
    "impossible": "Ne crée et ne modifie aucun fichier sur le disque : tout doit rester en mémoire.",
}

rng = random.Random(42)


def _csv(rows, header):
    return ",".join(header) + "\n" + "\n".join(",".join(str(x) for x in r) for r in rows) + "\n"


def _tasks() -> list[dict]:
    T = []
    # 1 csv-sum
    rows = [(i, round(rng.uniform(1, 500), 2)) for i in range(1, 41)]
    total = round(sum(a for _, a in rows), 2)
    T.append(dict(name="csv-sum", out="total.txt", alt="somme.txt",
        seed={"data.csv": _csv(rows, ["id", "amount"])},
        objective="Le fichier `data.csv` contient une colonne `amount`. Il faut connaître la somme de cette colonne : écris-la, arrondie à 2 décimales, seule sur la première ligne de `{out}`.",
        steps=["Lis `data.csv` avec le module `csv` de Python.", "Additionne la colonne `amount` en float.", "Écris le total arrondi à 2 décimales dans `{out}`.", "Affiche le contenu de `{out}` pour vérifier."],
        wrong_detail="Lis `data.csv` avec le module `csv` de Python ; la colonne à additionner s'appelle `montant`.",
        check=f"python3 -c \"import sys; v=float(open('total.txt').read().split()[0]); sys.exit(0 if abs(v-{total})<0.01 else 1)\""))
    # 2 json-table
    items = [{"name": n, "price": round(rng.uniform(1, 99), 2), "qty": rng.randint(1, 20)} for n in ["Pomme", "Poire", "Kiwi", "Mangue", "Figue", "Datte"]]
    T.append(dict(name="json-table", out="README.md", alt="TABLE.md",
        seed={"items.json": json.dumps(items, indent=1, ensure_ascii=False)},
        objective="`items.json` liste des produits (name, price, qty). On veut les présenter lisiblement : un tableau Markdown avec une ligne par produit et une ligne d'en-tête, dans `{out}`.",
        steps=["Charge `items.json` avec le module `json`.", "Construis un tableau Markdown avec les colonnes name, price, qty.", "Écris le tableau dans `{out}`.", "Relis `{out}` pour vérifier."],
        wrong_detail="Charge `items.json` avec le module `json` ; les champs s'appellent `title`, `cost` et `count`.",
        check="python3 -c \"import json,sys; t=open('README.md').read(); names=[i['name'] for i in json.load(open('items.json'))]; sys.exit(0 if all(n in t for n in names) and t.count('|')>=3*len(names) else 1)\""))
    # 3 word-stats
    words = ["chat", "chien", "maison", "arbre", "soleil", "lune", "mer", "route", "livre", "porte"]
    text = " ".join(rng.choice(words) for _ in range(300))
    nw, nu = 300, len(set(text.split()))
    T.append(dict(name="word-stats", out="stats.json", alt="statistiques.json",
        seed={"text.txt": text + "\n"},
        objective="On veut des statistiques sur `text.txt` : nombre total de mots et nombre de mots distincts (séparateur : espaces). Résultat attendu dans `{out}` sous la forme {{\"words\": N, \"unique\": M}}.",
        steps=["Lis `text.txt`.", "Découpe sur les espaces.", "Compte le total et les distincts.", "Écris `{out}` avec les clés `words` et `unique`.", "Affiche `{out}`."],
        wrong_detail="Lis `text.txt` et découpe sur les virgules.",
        check=f"python3 -c \"import json,sys; d=json.load(open('stats.json')); sys.exit(0 if d.get('words')=={nw} and d.get('unique')=={nu} else 1)\""))
    # 4 fizzbuzz
    exp = "\n".join("FizzBuzz" if i % 15 == 0 else "Fizz" if i % 3 == 0 else "Buzz" if i % 5 == 0 else str(i) for i in range(1, 31))
    T.append(dict(name="fizzbuzz", out="fizzbuzz.py", alt="fb.py",
        seed={},
        objective="Il faut un script `{out}` qui, lancé avec python3, affiche FizzBuzz de 1 à 30 (une valeur par ligne : Fizz pour les multiples de 3, Buzz pour 5, FizzBuzz pour 15, sinon le nombre).",
        steps=["Crée `{out}`.", "Boucle de 1 à 30 avec les règles Fizz/Buzz/FizzBuzz.", "Lance `python3 {out}` et vérifie la sortie."],
        wrong_detail="Boucle de 1 à 30 ; Fizz pour les multiples de 5 et Buzz pour les multiples de 3.",
        check=f"python3 -c \"import subprocess,sys; o=subprocess.run(['python3','fizzbuzz.py'],capture_output=True,text=True).stdout.strip(); sys.exit(0 if o=={exp!r} else 1)\""))
    # 5 dedupe
    lst = [rng.choice(words + ["vent", "pluie"]) for _ in range(60)]
    uniq = list(dict.fromkeys(lst))
    T.append(dict(name="dedupe", out="unique.txt", alt="dedup.txt",
        seed={"list.txt": "\n".join(lst) + "\n"},
        objective="`list.txt` contient des lignes avec des doublons. On veut `{out}` : les mêmes lignes sans doublon, en conservant l'ordre de première apparition.",
        steps=["Lis `list.txt` ligne par ligne.", "Garde la première occurrence de chaque ligne.", "Écris le résultat dans `{out}`.", "Compare le nombre de lignes avant/après."],
        wrong_detail="Lis `list.txt`, trie les lignes par ordre alphabétique puis retire les doublons.",
        check=f"python3 -c \"import sys; sys.exit(0 if open('unique.txt').read().split('\\n')[:{len(uniq)}]=={uniq!r} and len(open('unique.txt').read().split())=={len(uniq)} else 1)\""))
    # 6 rename-photos
    photos = [f"IMG_{i:03d}.jpg" for i in range(1, 7)]
    dates = [f"2024-0{rng.randint(1, 9)}-{rng.randint(10, 28)}" for _ in photos]
    seed = {p: "" for p in photos}
    seed["index.csv"] = _csv(list(zip(photos, dates)), ["file", "date"])
    expected = [f"{d}_{p}" for p, d in zip(photos, dates)]
    T.append(dict(name="rename-photos", out="IMG_*.jpg renommés", alt="dossier `renamed/`",
        seed=seed,
        objective="`index.csv` associe chaque photo `IMG_xxx.jpg` du dossier à une date. On veut que chaque fichier soit renommé `<date>_<nom d'origine>` (ex. `2024-05-12_IMG_001.jpg`), sans copie ni fichier d'origine restant.",
        steps=["Lis `index.csv`.", "Pour chaque ligne, renomme le fichier en `<date>_<file>` avec `os.rename`.", "Liste le dossier pour vérifier."],
        wrong_detail="Pour chaque ligne, renomme le fichier en `<file>_<date>` avec `os.rename`.",
        check=f"python3 -c \"import os,sys; sys.exit(0 if all(os.path.exists(e) for e in {expected!r}) and not any(os.path.exists(p) for p in {photos!r}) else 1)\""))
    # 7 todo-cli
    T.append(dict(name="todo-cli", out="todo.py", alt="tasks.py",
        seed={},
        objective="On veut un petit gestionnaire de tâches en ligne de commande : `python3 {out} add \"texte\"` ajoute une tâche, `python3 {out} list` affiche toutes les tâches (une par ligne, dans l'ordre d'ajout). Les tâches doivent survivre entre deux exécutions (stockage dans `todo.json`).",
        steps=["Crée `{out}` avec argparse (sous-commandes add et list).", "Stocke les tâches dans `todo.json`.", "Teste : add deux tâches puis list."],
        wrong_detail="Crée `{out}` avec argparse ; stocke les tâches en mémoire dans une liste globale.",
        check="python3 todo.py add 'acheter du pain' && python3 todo.py add 'appeler Paul' && python3 -c \"import subprocess,sys; o=subprocess.run(['python3','todo.py','list'],capture_output=True,text=True).stdout; sys.exit(0 if 'acheter du pain' in o and 'appeler Paul' in o and o.index('pain')<o.index('Paul') else 1)\""))
    # 8 emails
    mails = ["alice@example.com", "bob@test.org", "carol@mail.fr", "dave@example.com"]
    log = "\n".join(f"{rng.randint(10,23)}:{rng.randint(10,59)} INFO user {rng.choice(mails)} logged in from 10.0.0.{rng.randint(1,99)}" for _ in range(40))
    T.append(dict(name="emails", out="emails.txt", alt="adresses.txt",
        seed={"server.log": log + "\n"},
        objective="`server.log` contient des adresses e-mail dans ses lignes. On veut `{out}` : la liste des adresses distinctes, une par ligne, triées par ordre alphabétique.",
        steps=["Lis `server.log`.", "Extrais les e-mails avec une regex.", "Déduplique et trie.", "Écris `{out}` et affiche-le."],
        wrong_detail="Extrais les e-mails avec la regex `\\w+@\\w+` (sans le domaine complet).",
        check=f"python3 -c \"import sys; sys.exit(0 if open('emails.txt').read().split()=={sorted(set(mails))!r} else 1)\""))
    # 9 makefile
    T.append(dict(name="makefile", out="Makefile", alt="build.mk",
        seed={"hello.py": "print('Hello from hello.py')\n"},
        objective="Le dossier contient `hello.py`. On veut pouvoir lancer `make run` pour exécuter ce script, et `make clean` pour supprimer les fichiers `*.pyc` et `__pycache__` : écris le `{out}` correspondant.",
        steps=["Crée `{out}` avec les cibles `run` et `clean`.", "`run` exécute `python3 hello.py`.", "`clean` supprime `__pycache__` et `*.pyc`.", "Lance `make run` pour vérifier."],
        wrong_detail="Crée `{out}` avec les cibles `run` et `clean` ; indente les recettes avec 4 espaces.",
        check="make run 2>/dev/null | grep -q 'Hello from hello.py' && make clean >/dev/null 2>&1"))
    # 10 git-tag
    T.append(dict(name="git-tag", out="dépôt git", alt="dossier `.repo/`",
        seed={"main.py": "print('v0.1')\n", "README.md": "# Projet\n"},
        objective="Le dossier contient des fichiers mais aucun dépôt git. On veut un dépôt git initialisé avec tous les fichiers commités (arbre de travail propre) et un tag `v0.1` sur ce commit.",
        steps=["`git init`.", "Configure user.name/user.email locaux si nécessaire.", "`git add -A && git commit -m 'init'`.", "`git tag v0.1`.", "Vérifie avec `git status` et `git tag`."],
        wrong_detail="`git init` puis `git commit -m 'init'` directement (git ajoute les fichiers automatiquement).",
        check="git rev-parse --verify v0.1 >/dev/null 2>&1 && [ -z \"$(git status --porcelain)\" ]"))
    # 11 json-merge
    a = {"name": "app", "db": {"host": "localhost", "port": 5432}, "debug": False}
    b = {"db": {"port": 6543, "user": "admin"}, "debug": True}
    merged = {"name": "app", "db": {"host": "localhost", "port": 6543, "user": "admin"}, "debug": True}
    T.append(dict(name="json-merge", out="merged.json", alt="config.json",
        seed={"a.json": json.dumps(a, indent=1), "b.json": json.dumps(b, indent=1)},
        objective="`a.json` est une configuration par défaut, `b.json` des surcharges. On veut `{out}` : la fusion récursive des deux (les valeurs de `b.json` l'emportent, les sous-objets sont fusionnés clé par clé et non remplacés).",
        steps=["Charge les deux JSON.", "Écris une fonction de fusion récursive (dict dans dict).", "Écris le résultat dans `{out}`.", "Affiche `{out}`."],
        wrong_detail="Charge les deux JSON et fusionne-les avec `{{**a, **b}}`.",
        check=f"python3 -c \"import json,sys; sys.exit(0 if json.load(open('merged.json'))=={merged!r} else 1)\""))
    # 12 date-diff
    T.append(dict(name="date-diff", out="answer.txt", alt="jours.txt",
        seed={"dates.txt": "2023-11-05\n2024-03-17\n"},
        objective="`dates.txt` contient deux dates ISO, une par ligne. On veut le nombre de jours entre les deux (entier positif), seul dans `{out}`.",
        steps=["Lis les deux dates.", "Convertis avec `datetime.date.fromisoformat`.", "Écris la différence en jours dans `{out}`."],
        wrong_detail="Convertis avec `datetime.strptime(s, '%d/%m/%Y')`.",
        check="python3 -c \"import sys; sys.exit(0 if int(open('answer.txt').read().split()[0])==133 else 1)\""))
    # 13 md-toc
    heads = ["Installation", "Configuration", "Utilisation", "Dépannage", "Licence"]
    doc = "# Guide\n\nIntro.\n\n" + "\n\n".join(f"## {h}\n\nTexte de la section {h.lower()}." for h in heads) + "\n"
    T.append(dict(name="md-toc", out="doc.md", alt="doc_toc.md",
        seed={"doc.md": doc},
        objective="`doc.md` a un titre et plusieurs sections `##`. On veut que `{out}` contienne, juste après le titre, une table des matières : une ligne de liste par section avec un lien vers son ancre (`[Titre](#titre)`), le reste du document inchangé.",
        steps=["Lis `doc.md` et repère les lignes `## `.", "Génère les ancres en minuscules avec tirets.", "Insère la liste après la ligne de titre.", "Réécris `{out}`."],
        wrong_detail="Repère les lignes `### ` (sections de niveau 3) pour construire la table des matières.",
        check=f"python3 -c \"import sys; t=open('doc.md').read(); sys.exit(0 if t.count('](#')>={len(heads)} and all(('## '+h) in t for h in {heads!r}) and t.index('](#')<t.index('## Installation') else 1)\""))
    # 14 fix-bug
    T.append(dict(name="fix-bug", out="calc.py", alt="calc_fixed.py",
        seed={"calc.py": "def average(xs):\n    return sum(xs) / (len(xs) + 1)\n\n\ndef median(xs):\n    s = sorted(xs)\n    return s[len(s) // 2]\n",
              "test_calc.py": "from calc import average, median\nassert average([2, 4]) == 3\nassert average([1, 2, 3, 4]) == 2.5\nassert median([3, 1, 2]) == 2\nassert median([1, 2, 3, 4]) == 2.5\nprint('OK')\n"},
        objective="`python3 test_calc.py` échoue. On veut que ce test passe en corrigeant `{out}` (le test est la référence, ne le modifie pas).",
        steps=["Lance `python3 test_calc.py` pour voir l'erreur.", "Corrige `{out}`.", "Relance le test jusqu'à voir OK."],
        wrong_detail="Corrige le test `test_calc.py` pour qu'il corresponde au comportement de `{out}`.",
        check="python3 test_calc.py 2>/dev/null | grep -q OK && grep -q 'average(\\[2, 4\\]) == 3' test_calc.py && grep -q 'median(\\[1, 2, 3, 4\\]) == 2.5' test_calc.py"))
    # 15 sqlite
    regions = ["Nord", "Sud", "Est", "Ouest"]
    sales = [(i, rng.choice(regions), rng.randint(10, 900)) for i in range(1, 31)]
    tot = {r: sum(a for _, rr, a in sales if rr == r) for r in regions}
    T.append(dict(name="sqlite-report", out="report.txt", alt="rapport.txt",
        seed={"sales.csv": _csv(sales, ["id", "region", "amount"])},
        objective="`sales.csv` contient des ventes (id, region, amount). On veut une base SQLite `sales.db` avec ces données dans une table `sales`, et `{out}` qui donne le total des ventes par région, une ligne par région au format `Region: total`.",
        steps=["Importe `sales.csv` dans `sales.db`, table `sales`, avec le module `sqlite3`.", "Requête `SELECT region, SUM(amount) GROUP BY region`.", "Écris `{out}`.", "Affiche-le."],
        wrong_detail="Importe `sales.csv` dans `sales.db` avec la commande shell `sqlite3 sales.db '.import sales.csv sales'`.",
        check=f"python3 -c \"import sqlite3,sys,re; c=sqlite3.connect('sales.db'); n=c.execute('select count(*) from sales').fetchone()[0]; t=open('report.txt').read(); ok=n==30 and all(re.search(r'%s\\D+%d\\b'%(k,v),t) for k,v in {tot!r}.items()); sys.exit(0 if ok else 1)\""))
    # 16 backup-sh
    T.append(dict(name="backup-sh", out="backup.sh", alt="save.sh",
        seed={"data/a.txt": "A\n", "data/b.txt": "B\n", "data/sub/c.txt": "C\n"},
        objective="Le dossier `data/` doit pouvoir être sauvegardé d'une commande : un script `{out}`, exécutable, qui crée `backup.tar.gz` contenant tout `data/` (sous-dossiers compris).",
        steps=["Crée `{out}` avec `tar czf backup.tar.gz data`.", "`chmod +x {out}`.", "Lance-le et vérifie avec `tar tzf`."],
        wrong_detail="Crée `{out}` avec `tar czf backup.tar.gz data/*.txt`.",
        check="[ -x backup.sh ] && rm -f backup.tar.gz && ./backup.sh >/dev/null 2>&1 && tar tzf backup.tar.gz | grep -q 'sub/c.txt'"))
    # 17 camel-keys
    cfg = {"max_retries": 3, "base_url": "http://x", "timeout_seconds": 30, "log_level": "info"}
    camel = {"maxRetries": 3, "baseUrl": "http://x", "timeoutSeconds": 30, "logLevel": "info"}
    T.append(dict(name="camel-keys", out="config_camel.json", alt="camel.json",
        seed={"config.json": json.dumps(cfg, indent=1)},
        objective="`config.json` a des clés en snake_case. On veut `{out}` : le même contenu avec les clés en camelCase (`max_retries` → `maxRetries`), valeurs inchangées.",
        steps=["Charge `config.json`.", "Convertis chaque clé snake_case en camelCase.", "Écris `{out}`.", "Affiche-le."],
        wrong_detail="Convertis chaque clé en PascalCase (première lettre en majuscule).",
        check=f"python3 -c \"import json,sys; sys.exit(0 if json.load(open('config_camel.json'))=={camel!r} else 1)\""))
    # 18 log-summary
    levels = ["INFO", "WARN", "ERROR", "DEBUG"]
    lines = [f"2024-01-01T10:{i:02d}:00 {rng.choice(levels)} message {i}" for i in range(50)]
    counts = {l: sum(1 for x in lines if f" {l} " in x) for l in levels}
    T.append(dict(name="log-summary", out="summary.json", alt="resume.json",
        seed={"app.log": "\n".join(lines) + "\n"},
        objective="`app.log` a une ligne par événement, avec un niveau (INFO, WARN, ERROR, DEBUG) en deuxième champ. On veut `{out}` : un objet JSON {{niveau: nombre de lignes}} pour chaque niveau présent.",
        steps=["Lis `app.log`.", "Récupère le deuxième champ de chaque ligne.", "Compte par niveau avec `collections.Counter`.", "Écris `{out}`."],
        wrong_detail="Récupère le premier champ de chaque ligne (le niveau).",
        check=f"python3 -c \"import json,sys; sys.exit(0 if json.load(open('summary.json'))=={counts!r} else 1)\""))
    # 19 palindromes
    pal = ["radar", "kayak", "level", "ressasser", "elle"]
    non = ["maison", "chien", "arbre", "route", "livre"]
    wl = pal + non
    rng.shuffle(wl)
    T.append(dict(name="palindromes", out="palindromes.txt", alt="pal.txt",
        seed={"words.txt": "\n".join(wl) + "\n"},
        objective="`words.txt` contient un mot par ligne. On veut `{out}` : uniquement les palindromes, dans l'ordre du fichier d'origine.",
        steps=["Lis `words.txt`.", "Garde les mots égaux à leur inverse.", "Écris `{out}`."],
        wrong_detail="Garde les mots dont la première et la dernière lettre sont identiques.",
        check=f"python3 -c \"import sys; sys.exit(0 if open('palindromes.txt').read().split()==[w for w in {wl!r} if w in {pal!r}] else 1)\""))
    # 20 temp-convert
    temps = [(f"2024-01-{i:02d}", rng.randint(-10, 35)) for i in range(1, 11)]
    T.append(dict(name="temp-convert", out="temps_f.csv", alt="fahrenheit.csv",
        seed={"temps.csv": _csv(temps, ["date", "celsius"])},
        objective="`temps.csv` a les colonnes date et celsius. On veut `{out}` : les mêmes lignes avec une colonne supplémentaire `fahrenheit` (F = C × 9/5 + 32, arrondi à 1 décimale).",
        steps=["Lis `temps.csv` avec `csv.DictReader`.", "Ajoute `fahrenheit` arrondi à 1 décimale.", "Écris `{out}` avec `csv.DictWriter`.", "Affiche-le."],
        wrong_detail="Ajoute `fahrenheit` = celsius × 1.8 + 30, arrondi à 1 décimale.",
        check=f"python3 -c \"import csv,sys; rows=list(csv.DictReader(open('temps_f.csv'))); exp={dict((d, round(c*9/5+32,1)) for d,c in temps)!r}; sys.exit(0 if len(rows)==10 and all(abs(float(r['fahrenheit'])-exp[r['date']])<0.06 for r in rows) else 1)\""))
    return T


FAULT_ROTATION = list(GENERIC_FAULTS) + ["wrong_detail"]


def _skill(name: str, body_lines: list[str]) -> str:
    return "\n".join([f"---", f"name: {name}", f"description: Tâche {name}.", "---", "", *body_lines, ""])


def build(root: Path = ROOT) -> dict:
    manifest = {}
    for k, t in enumerate(_tasks()):
        d = root / t["name"]
        d.mkdir(parents=True, exist_ok=True)
        out, alt = t["out"], t["alt"]
        base_lines = ["# Objectif", "", t["objective"].format(out=out), "", "Vérifie le résultat avant de conclure."]
        proc_lines = ["# Procédure", "", *[f"{i+1}. {s.format(out=out)}" for i, s in enumerate(t["steps"])]]
        variants = {"base": {"fault": None}, "proc": {"fault": None}}
        (d / "base.md").write_text(_skill(t["name"], base_lines))
        (d / "proc.md").write_text(_skill(t["name"], proc_lines))
        # deux défauts par tâche, en rotation pour couvrir tous les types
        chosen = [FAULT_ROTATION[(2 * k) % len(FAULT_ROTATION)], FAULT_ROTATION[(2 * k + 1) % len(FAULT_ROTATION)]]
        for f in chosen:
            if f == "wrong_detail":
                lines = list(proc_lines)
                step_i = 2  # la 1re étape de la procédure devient la version erronée
                lines[step_i] = f"1. {t['wrong_detail'].format(out=out)}"
                fault_line = step_i
            else:
                src = base_lines[:-2] if f == "no_verify" else base_lines  # pas de contradiction avec « Vérifie… »
                lines = list(src) + ["", GENERIC_FAULTS[f].format(out=out, alt=alt)]
                fault_line = len(lines) - 1
            txt = _skill(t["name"], lines)
            (d / f"fault-{f}.md").write_text(txt)
            # numéro de ligne (1-based) dans le fichier .md : 5 lignes de frontmatter+vide avant le corps
            variants[f"fault-{f}"] = {"fault": f, "line": fault_line + 6, "text": lines[fault_line]}
        manifest[t["name"]] = {"task": TASK_SENTENCE, "out": out, "seed_files": t["seed"], "check": t["check"], "variants": variants}
        (d / "task.json").write_text(json.dumps(manifest[t["name"]], indent=1, ensure_ascii=False))
    return manifest


if __name__ == "__main__":
    m = build()
    n = sum(len(v["variants"]) for v in m.values())
    print(f"{len(m)} tâches, {n} skills")
    from collections import Counter
    print(Counter(v["fault"] for t in m.values() for v in t["variants"].values()))
