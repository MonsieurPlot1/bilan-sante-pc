"""Lance les modules, calcule le score et prépare le rapport texte.

Sans PySide6 : ce code tourne dans le thread d'analyse et se teste sans interface.
"""

import ctypes
import html
import logging
import re
import time
from contextlib import contextmanager
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Callable

import config
from journal import dossier_par_defaut
from modules import batterie, demarrage, disque, redemarrage, ressources, score
from modules.disque import taille_lisible

journal = logging.getLogger(__name__)
AIDE = f"Les détails sont dans le journal : {dossier_par_defaut() / 'bilan.log'}"

# (clé, nom affiché, fonction scan), dans l'ordre d'affichage.
MODULES: list[tuple[str, str, Callable[[], dict]]] = [
    ("demarrage", "Démarrage", demarrage.scan),
    ("disque", "Disque", disque.scan),
    ("ressources", "Mémoire et processeur", ressources.scan),
    ("redemarrage", "Redémarrage", redemarrage.scan),
    ("batterie", "Batterie", batterie.scan),
]
NOMS = {cle: nom for cle, nom, _ in MODULES}

THREAD_MODE_BACKGROUND_BEGIN = 0x00010000
THREAD_MODE_BACKGROUND_END = 0x00020000


@contextmanager
def arriere_plan():
    """Mode arrière-plan de Windows pour le thread courant : processeur, disque et mémoire
    en priorité basse, pour que l'analyse ne ralentisse pas ce que l'utilisateur fait à côté."""
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentThread.restype = wintypes.HANDLE
    kernel32.SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]
    actif = kernel32.SetThreadPriority(kernel32.GetCurrentThread(), THREAD_MODE_BACKGROUND_BEGIN)
    try:
        yield
    finally:
        if actif:
            kernel32.SetThreadPriority(kernel32.GetCurrentThread(), THREAD_MODE_BACKGROUND_END)


def analyser() -> dict:
    """Lance chaque module ; un module qui plante n'empêche pas les autres.

    Dans "modules" : le résultat de chaque module, None s'il a planté ;
    un module « non applicable » (batterie d'un PC fixe) n'y figure pas.
    """
    debut = time.perf_counter()
    modules, erreurs = {}, {}
    with arriere_plan():
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


STYLE_HTML = """
body { font-family: "Segoe UI", Arial, sans-serif; max-width: 860px; margin: 24px auto; padding: 0 16px;
       color: #1f2328; background: #ffffff; line-height: 1.45; }
h1 { margin-bottom: 0; } .discret { color: #59636e; }
.score { font-size: 48px; font-weight: bold; margin: 16px 0 0; }
section { border: 1px solid #d1d9e0; border-radius: 8px; padding: 4px 16px 12px; margin: 16px 0; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 4px 8px; border-bottom: 1px solid #eef1f4; overflow-wrap: anywhere; }
th { color: #59636e; font-weight: 600; }
"""
COULEURS_HTML = {"vert": "#1a7f37", "orange": "#bc4c00", "rouge": "#cf222e", "gris": "#59636e"}


def anonymiser(texte: str) -> str:
    """Remplace le dossier personnel (qui contient le nom d'utilisateur) par %USERPROFILE%."""
    return re.sub(re.escape(str(Path.home())), "%USERPROFILE%", texte, flags=re.IGNORECASE)


def _tableau(colonnes: list[str], lignes: list[list[str]]) -> str:
    if not lignes:
        return ""
    entete = "".join(f"<th>{html.escape(c)}</th>" for c in colonnes)
    corps = "".join("<tr>" + "".join(f"<td>{html.escape(anonymiser(str(v)))}</td>" for v in ligne) + "</tr>"
                    for ligne in lignes)
    return f"<table><tr>{entete}</tr>{corps}</table>"


def _detail(cle: str, module: dict) -> str:
    if cle == "demarrage":
        return _tableau(["Programme", "Éditeur", "Chemin"],
                        [[p["nom"], p["editeur"] or "inconnu", p["chemin"]] for p in module["programmes"]])
    if cle == "disque":
        return _tableau(["Plus gros dossiers du profil", "Taille"],
                        [[d["chemin"], taille_lisible(d["taille"])] for d in module["gros_dossiers"]])
    if cle == "ressources":
        return _tableau(["Programmes gourmands en mémoire", "Mémoire"],
                        [[p["nom"], taille_lisible(p["octets"])] for p in module["processus"]])
    return ""


def rapport_html(resultat: dict) -> str:
    """Rapport autonome (un seul fichier, sans ressource externe), sans nom d'utilisateur."""
    note = score_global(resultat)
    niveau, phrase = interpretation(note)
    e = html.escape
    parties = ["<h1>Bilan santé PC</h1>",
               f"<p class='discret'>Analyse du {resultat['date']:%d/%m/%Y à %H:%M} - version {config.VERSION} "
               f"(calcul du score v{config.SCORE_VERSION})</p>",
               f"<p class='score' style='color:{COULEURS_HTML[niveau]}'>{note if note is not None else '?'} / 100</p>",
               f"<p>{e(phrase)}</p>"]
    conseils_ = conseils(resultat)
    if conseils_:
        parties.append("<section><h2>Conseils</h2><ol>"
                       + "".join(f"<li>{e(anonymiser(c))}</li>" for c in conseils_) + "</ol></section>")
    for cle, module in resultat["modules"].items():
        lignes = [resultat["erreurs"][cle]] if module is None else module["constats"]
        parties.append(f"<section><h2>{e(NOMS[cle])} : {e(points_module(resultat, cle))}</h2>"
                       + "".join(f"<p>{e(anonymiser(ligne))}</p>" for ligne in lignes)
                       + (_detail(cle, module) if module else "") + "</section>")
    if "score" in resultat["erreurs"]:
        parties.append(f"<p>{e(anonymiser(resultat['erreurs']['score']))}</p>")
    parties.append("<p class='discret'>Rapport créé sur ce PC par Bilan santé PC. "
                   "L'application ne modifie rien et n'envoie aucune donnée.</p>")
    return ("<!doctype html>\n<html lang='fr'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>Bilan santé PC - {resultat['date']:%d/%m/%Y}</title><style>{STYLE_HTML}</style></head>"
            f"<body>{''.join(parties)}</body></html>\n")
