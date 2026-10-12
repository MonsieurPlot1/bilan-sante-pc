"""Lance les modules, calcule le score et prépare le rapport texte.

Sans PySide6 : ce code tourne dans le thread d'analyse et se teste sans interface.
"""

import logging
import time
from typing import Callable

import config
from journal import dossier_par_defaut
from modules import demarrage, disque, score

journal = logging.getLogger(__name__)
AIDE = f"Les détails sont dans le journal : {dossier_par_defaut() / 'bilan.log'}"

# (clé, nom affiché, fonction scan, résultat neutre si le module plante)
MODULES: list[tuple[str, str, Callable[[], dict], dict]] = [
    ("demarrage", "Démarrage", demarrage.scan, {"constats": [], "programmes": []}),
    ("disque", "Disque", disque.scan, {"constats": [], "disques": [], "gros_dossiers": []}),
]


def analyser() -> dict:
    """Lance chaque module ; un module qui plante n'empêche pas les autres."""
    debut = time.perf_counter()
    resultats, erreurs = {}, {}
    for cle, nom, scan, neutre in MODULES:
        try:
            resultats[cle] = scan()
        except Exception:  # on veut isoler n'importe quelle panne du module
            journal.exception("Échec du module %s", nom)
            erreurs[cle] = f"L'analyse « {nom} » n'a pas pu aboutir. {AIDE}"
            # Le résultat neutre donne tous les points et aucun conseil pour ce module.
            resultats[cle] = neutre

    try:
        bilan = score.calculer(resultats["demarrage"], resultats["disque"])
    except Exception:
        journal.exception("Échec du calcul du score")
        bilan = None
        erreurs["score"] = f"Le score n'a pas pu être calculé. {AIDE}"

    duree = time.perf_counter() - debut
    journal.info("Analyse terminée en %.1f s (erreurs : %s)", duree, list(erreurs) or "aucune")
    return {**resultats, "bilan": bilan, "erreurs": erreurs, "duree": duree}


def score_global(resultat: dict) -> int | None:
    """Score /100, ou None si une partie a planté (un score partiel serait trompeur)."""
    if resultat["erreurs"] or resultat["bilan"] is None:
        return None
    return resultat["bilan"]["score"]


def interpretation(note: int | None) -> tuple[str, str]:
    """Niveau (vert, orange, rouge, gris) et phrase en français simple."""
    if note is None:
        return "gris", "Analyse incomplète : une partie n'a pas pu être vérifiée."
    if note >= 80:
        return "vert", "Ton PC est en bonne forme."
    if note >= 50:
        return "orange", "Ton PC va bien, mais quelques réglages l'aideraient à aller plus vite."
    return "rouge", "Ton PC est encombré : les conseils ci-dessous peuvent vraiment l'aider."


def rapport_texte(resultat: dict) -> str:
    """Résumé texte à coller dans un message (bouton « Copier le rapport »)."""
    note = score_global(resultat)
    lignes = [f"Bilan santé PC v{config.VERSION}",
              f"Score : {note if note is not None else '?'} / 100 - {interpretation(note)[1]}"]
    bilan = resultat["bilan"]
    for cle, nom, _, _ in MODULES:
        lignes.append("")
        if cle in resultat["erreurs"]:
            lignes += [f"{nom} : erreur", resultat["erreurs"][cle]]
            continue
        maximum = config.POINTS_DEMARRAGE if cle == "demarrage" else config.POINTS_DISQUE
        lignes.append(f"{nom} : {bilan['scores'][cle]} / {maximum}" if bilan else nom)
        lignes += resultat[cle]["constats"]
    if bilan and bilan["conseils"]:
        lignes += ["", "Conseils :"]
        lignes += [f"{numero}. {conseil}" for numero, conseil in enumerate(bilan["conseils"], start=1)]
    if "score" in resultat["erreurs"]:
        lignes += ["", resultat["erreurs"]["score"]]
    lignes += ["", f"Analyse faite en {resultat['duree']:.0f} s."]
    return "\n".join(lignes)
