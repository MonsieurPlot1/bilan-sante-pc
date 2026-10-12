"""Lance les modules, calcule le score et prépare le rapport texte.

Sans PySide6 : ce code tourne dans le thread d'analyse et se teste sans interface.
"""

import logging
import time
from datetime import datetime
from typing import Callable

import config
from journal import dossier_par_defaut
from modules import batterie, demarrage, disque, ressources, score

journal = logging.getLogger(__name__)
AIDE = f"Les détails sont dans le journal : {dossier_par_defaut() / 'bilan.log'}"

# (clé, nom affiché, fonction scan), dans l'ordre d'affichage.
MODULES: list[tuple[str, str, Callable[[], dict]]] = [
    ("demarrage", "Démarrage", demarrage.scan),
    ("disque", "Disque", disque.scan),
    ("ressources", "Mémoire et processeur", ressources.scan),
    ("batterie", "Batterie", batterie.scan),
]
NOMS = {cle: nom for cle, nom, _ in MODULES}


def analyser() -> dict:
    """Lance chaque module ; un module qui plante n'empêche pas les autres.

    Dans "modules" : le résultat de chaque module, None s'il a planté ;
    un module « non applicable » (batterie d'un PC fixe) n'y figure pas.
    """
    debut = time.perf_counter()
    modules, erreurs = {}, {}
    for cle, nom, scan in MODULES:
        try:
            resultat = scan()
        except Exception:  # on veut isoler n'importe quelle panne du module
            journal.exception("Échec du module %s", nom)
            erreurs[cle] = f"L'analyse « {nom} » n'a pas pu aboutir. {AIDE}"
            modules[cle] = None
            continue
        if resultat.get("applicable", True):
            modules[cle] = resultat

    try:
        bilan = score.calculer(modules)
    except Exception:
        journal.exception("Échec du calcul du score")
        bilan = None
        erreurs["score"] = f"Le score n'a pas pu être calculé. {AIDE}"

    duree = time.perf_counter() - debut
    journal.info("Analyse terminée en %.1f s (erreurs : %s)", duree, list(erreurs) or "aucune")
    return {"modules": modules, "bilan": bilan, "erreurs": erreurs, "duree": duree, "date": datetime.now()}


def score_global(resultat: dict) -> int | None:
    """Score /100, ou None si une partie a planté (un score partiel serait trompeur)."""
    return resultat["bilan"]["score"] if resultat["bilan"] else None


def points_module(resultat: dict, cle: str) -> str:
    """« 21 / 30 » pour un module, « erreur », ou « hors score » (usure de batterie non mesurable)."""
    bilan = resultat["bilan"]
    if resultat["modules"].get(cle) is None or not bilan:
        return "erreur"
    if cle not in bilan["scores"]:
        return "hors score"
    return f"{bilan['scores'][cle]} / {bilan['bareme'][cle]}"


def interpretation(note: int | None) -> tuple[str, str]:
    """Niveau (vert, orange, rouge, gris) et phrase en français simple."""
    if note is None:
        return "gris", "Analyse incomplète : une partie n'a pas pu être vérifiée."
    if note >= 80:
        return "vert", "Ton PC est en bonne forme."
    if note >= 50:
        return "orange", "Ton PC va bien, mais quelques réglages l'aideraient à aller plus vite."
    return "rouge", "Ton PC est encombré : les conseils ci-dessous peuvent vraiment l'aider."


def conseils(resultat: dict) -> list[str]:
    return resultat["bilan"]["conseils"] if resultat["bilan"] else []


def rapport_texte(resultat: dict) -> str:
    """Résumé texte à coller dans un message (bouton « Copier le rapport »)."""
    note = score_global(resultat)
    lignes = [f"Bilan santé PC v{config.VERSION} - {resultat['date']:%d/%m/%Y %H:%M}",
              f"Score : {note if note is not None else '?'} / 100 - {interpretation(note)[1]}"]
    for cle, module in resultat["modules"].items():
        lignes += ["", f"{NOMS[cle]} : {points_module(resultat, cle)}"]
        lignes += [resultat["erreurs"][cle]] if module is None else module["constats"]
    if conseils(resultat):
        lignes += ["", "Conseils :"]
        lignes += [f"{numero}. {conseil}" for numero, conseil in enumerate(conseils(resultat), start=1)]
    if "score" in resultat["erreurs"]:
        lignes += ["", resultat["erreurs"]["score"]]
    lignes += ["", f"Analyse faite en {resultat['duree']:.0f} s (calcul du score v{config.SCORE_VERSION})."]
    return "\n".join(lignes)
