"""Lance les modules, calcule le score et prépare le rapport texte.

Sans PySide6 : ce code tourne dans le thread d'analyse et se teste sans interface.
"""

import ctypes
import html
import logging
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Callable

import config
from journal import dossier_par_defaut
from modules import alimentation, batterie, demarrage, disque, fichiers, jeux, pilotes, redemarrage, ressources, score
from modules.disque import taille_lisible

journal = logging.getLogger(__name__)
AIDE = f"Les détails sont dans le journal : {dossier_par_defaut() / 'bilan.log'}"

# (clé, nom affiché, fonction scan), dans l'ordre d'affichage.
MODULES: list[tuple[str, str, Callable[[], dict]]] = [
    ("demarrage", "Démarrage", demarrage.scan),
    ("disque", "Disque", disque.scan),
    ("fichiers", "Fichiers inutiles", fichiers.scan),
    ("ressources", "Mémoire et processeur", ressources.scan),
    ("redemarrage", "Redémarrage", redemarrage.scan),
    ("alimentation", "Alimentation", alimentation.scan),
    ("jeux", "Jeux et affichage", jeux.scan),
    ("pilotes", "Pilotes", pilotes.scan),
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


def _en_arriere_plan(scan: Callable[[], dict]) -> dict:
    with arriere_plan():
        return scan()


def analyser(progression: Callable[[int, int, str], None] = lambda *_: None) -> dict:
    """Lance les modules en même temps ; un module qui plante n'empêche pas les autres.

    En même temps : la mesure du processeur (3 s d'attente) et les petites parties se font pendant la
    mesure des dossiers, la plus longue, qui fixe seule la durée de l'analyse.
    Dans "modules" : le résultat de chaque module (dans l'ordre de MODULES), None s'il a planté ;
    un module « non applicable » (batterie d'un PC fixe) n'y figure pas.
    `progression(finies, total, nom)` : au départ puis à chaque partie finie, le nombre de parties finies et
    le nom d'une partie encore en cours.
    """
    debut = time.perf_counter()
    resultats, erreurs = {}, {}
    restants = [nom for _, nom, _ in MODULES]
    progression(0, len(MODULES), restants[0])
    with ThreadPoolExecutor(max_workers=len(MODULES), thread_name_prefix="analyse") as executeur:
        taches = {executeur.submit(_en_arriere_plan, scan): (cle, nom) for cle, nom, scan in MODULES}
        for tache in as_completed(taches):
            cle, nom = taches[tache]
            try:
                resultats[cle] = tache.result()
            except Exception:  # on veut isoler n'importe quelle panne du module
                journal.exception("Échec du module %s", nom)
                erreurs[cle] = f"L'analyse « {nom} » n'a pas pu aboutir. {AIDE}"
            restants.remove(nom)
            if restants:
                progression(len(MODULES) - len(restants), len(MODULES), restants[0])
    modules = {cle: resultats.get(cle) for cle, _, _ in MODULES
               if cle in erreurs or resultats[cle].get("applicable", True)}

    try:
        bilan = score.calculer(modules)
    except Exception:
        journal.exception("Échec du calcul du score")
        bilan = None
        erreurs["score"] = f"Le score n'a pas pu être calculé. {AIDE}"

    duree = time.perf_counter() - debut
    journal.info("Analyse terminée en %.1f s (erreurs : %s)", duree, list(erreurs) or "aucune")
    return {"modules": modules, "bilan": bilan, "erreurs": erreurs, "duree": duree, "date": datetime.now()}


def echec() -> dict:
    """Résultat d'une analyse qui n'a pas pu aller au bout (panne imprévue en dehors des modules)."""
    return {"modules": {}, "bilan": None, "erreurs": {"score": f"L'analyse n'a pas pu aboutir. {AIDE}"},
            "duree": 0.0, "date": datetime.now()}


# Colonnes du détail dépliable de chaque carte, et des tableaux du rapport (sans colonnes : pas de détail).
COLONNES = {"demarrage": ["Programme", "Éditeur", "Chemin"], "disque": ["Élément", "Taille", "Détail"],
            "fichiers": [], "ressources": ["Programme", "Mémoire"], "redemarrage": [], "alimentation": [],
            "jeux": [], "pilotes": ["Appareil", "Pilote installé", "Mise à jour"], "batterie": []}


def lignes_detail(cle: str, module: dict) -> list[list[str]]:
    """Lignes du détail dépliable d'une carte, et du tableau de cette partie dans le rapport."""
    if cle == "demarrage":
        return [[p["nom"], p["editeur"] or "inconnu", p["chemin"]] for p in module["programmes"]]
    if cle == "pilotes":
        return lignes_pilotes(module)
    if cle == "disque":
        lignes = [[f"Disque {d['disque'].rstrip(os.sep)}", taille_lisible(d["libre"]) + " libres",
                   f"{d['pourcentage']:.0f} % utilisé sur {taille_lisible(d['total'])}"] for d in module["disques"]]
        return lignes + [[d["chemin"], taille_lisible(d["taille"]), "dossier du profil"]
                         for d in module["gros_dossiers"]]
    if cle == "ressources":
        return [[p["nom"], taille_lisible(p["octets"])] for p in module["processus"]]
    return []


def lignes_pilotes(module: dict) -> list[list[str]]:
    """Ce qui s'installe d'un clic d'abord, puis chaque pilote des composants du PC, du plus vieux au plus récent."""
    nvidia, lignes = module["nvidia"], []
    if pilotes.nvidia_a_installer(nvidia):
        lignes.append([nvidia["carte"], nvidia["installee"], f"{nvidia['derniere']['version']} disponible (NVIDIA)"])
    for mise_a_jour in module["mises_a_jour"] or []:
        lignes.append([mise_a_jour["nom"], "", "Windows Update"])
    a_verifier = f"à vérifier avec {module['outil']['nom']}" if module["outil"] else "à vérifier chez le fabricant"
    for pilote in module["pilotes"]:
        if lignes and pilotes.nvidia_a_installer(nvidia) and pilote["nom"] == nvidia["carte"]:
            continue  # déjà en tête
        quand = f" du {pilote['date']:%d/%m/%Y}" if pilote["date"] else ""
        lignes.append([pilote["nom"], pilote["version"] + quand, a_verifier if pilote in module["anciens"] else ""])
    return lignes


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


# Mot court affiché au-dessus de la phrase d'interprétation (la couleur n'est jamais seule).
ETATS = {"vert": "Bon état", "orange": "À surveiller", "rouge": "À améliorer", "gris": "Analyse incomplète"}


def niveau_ratio(ratio: float) -> str:
    """Niveau de couleur d'une partie selon la part de points gardés."""
    return "vert" if ratio >= 0.8 else "orange" if ratio >= 0.5 else "rouge"


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
:root { color-scheme: light dark; --fond: #f4f5f9; --carte: #ffffff; --texte: #1d1d1f; --texte-2: #5e5e64;
        --trait: #e3e6ee; --piste: #e8ebf3; --vert: #1e7b34; --orange: #c93400; --rouge: #d70015;
        --vif-vert: #34c759; --vif-orange: #ff9500; --vif-rouge: #ff3b30; --vif-gris: #8e8e93; }
@media (prefers-color-scheme: dark) {
  :root { --fond: #12151f; --carte: #1c2030; --texte: #f5f5f7; --texte-2: #ababb1; --trait: #2c3142;
          --piste: #2a2f40; --vert: #30d158; --orange: #ff9f0a; --rouge: #ff6961;
          --vif-vert: #30d158; --vif-orange: #ff9f0a; --vif-rouge: #ff453a; --vif-gris: #98989e; }
}
* { box-sizing: border-box; }
body { font-family: "Segoe UI Variable Text", "Segoe UI", Arial, sans-serif; max-width: 880px; margin: 0 auto;
       padding: 28px 16px 40px; color: var(--texte); background: var(--fond); line-height: 1.5; font-size: 15px; }
h1, h2, .phrase { font-family: "Segoe UI Variable Display", "Segoe UI", Arial, sans-serif; margin: 0; }
h1 { font-size: 24px; } h2 { font-size: 17px; }
.discret { color: var(--texte-2); font-size: 13px; margin: 2px 0 0; }
.carte { background: var(--carte); border: 1px solid var(--trait); border-radius: 20px; padding: 18px 22px;
         margin: 14px 0; box-shadow: 0 6px 18px rgba(29, 36, 64, .07); }
.tete { display: flex; gap: 28px; align-items: center; }
.anneau { flex: none; }
.phrase { font-size: 21px; font-weight: 700; margin: 8px 0 0; }
.pastille { display: inline-block; border-radius: 9px; padding: 2px 10px; font-size: 12.5px; font-weight: 600;
            white-space: nowrap; }
.pastille.vert { color: var(--vert); background: rgba(52, 199, 89, .16); }
.pastille.orange { color: var(--orange); background: rgba(255, 149, 0, .16); }
.pastille.rouge { color: var(--rouge); background: rgba(255, 59, 48, .14); }
.pastille.gris { color: var(--texte-2); background: rgba(128, 128, 140, .15); }
section header { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 8px; }
section p { margin: 2px 0; color: var(--texte-2); }
p.erreur { color: var(--rouge); }
ol.conseils { margin: 10px 0 0; padding-left: 22px; } ol.conseils li { margin: 8px 0; padding-left: 4px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; margin-top: 12px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--trait); overflow-wrap: anywhere;
         vertical-align: top; }
th { color: var(--texte-2); font-weight: 600; }
footer { margin-top: 18px; }
@media print { body { background: #ffffff; } .carte { box-shadow: none; break-inside: avoid; } }
"""


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


def _anneau(note: int | None, niveau: str) -> str:
    """Le score en anneau, comme dans l'application (dessiné en SVG : rien d'externe)."""
    texte = "?" if note is None else str(note)
    tour = 2 * math.pi * 52
    arc = (f"<circle cx='68' cy='68' r='52' fill='none' stroke='var(--vif-{niveau})' stroke-width='12' "
           f"stroke-linecap='round' stroke-dasharray='{tour * note / 100:.1f} {tour:.1f}' transform='rotate(-90 68 68)'/>"
           if note else "")
    return (f"<svg class='anneau' width='136' height='136' viewBox='0 0 136 136' role='img' "
            f"aria-label='Score : {texte} sur 100'>"
            "<circle cx='68' cy='68' r='52' fill='none' stroke='var(--piste)' stroke-width='12'/>"
            f"{arc}<text x='68' y='78' text-anchor='middle' font-size='34' font-weight='700' fill='currentColor'>"
            f"{texte}</text><text x='68' y='98' text-anchor='middle' font-size='11' fill='var(--texte-2)'>sur 100</text>"
            "</svg>")


def niveau_points(resultat: dict, cle: str) -> str:
    """Couleur de la pastille des points d'une partie : rouge en erreur, grise hors score."""
    bilan = resultat["bilan"]
    if resultat["modules"].get(cle) is None or not bilan:
        return "rouge"
    if cle not in bilan["scores"]:
        return "gris"
    return niveau_ratio(bilan["scores"][cle] / bilan["bareme"][cle])


def rapport_html(resultat: dict) -> str:
    """Rapport autonome (un seul fichier, sans ressource externe), sans nom d'utilisateur, dans l'allure de
    l'application (clair ou sombre comme le navigateur)."""
    note = score_global(resultat)
    niveau, phrase = interpretation(note)
    e = html.escape
    parties = ["<h1>Bilan santé PC</h1>",
               f"<p class='discret'>Analyse du {resultat['date']:%d/%m/%Y à %H:%M} · version {config.VERSION} "
               f"(calcul du score v{config.SCORE_VERSION})</p>",
               f"<div class='carte tete'>{_anneau(note, niveau)}<div><span class='pastille {niveau}'>"
               f"{e(ETATS[niveau])}</span><p class='phrase'>{e(phrase)}</p></div></div>"]
    conseils_ = conseils(resultat)
    if conseils_:
        parties.append("<section class='carte'><h2>Conseils</h2><ol class='conseils'>"
                       + "".join(f"<li>{e(anonymiser(c))}</li>" for c in conseils_) + "</ol></section>")
    for cle, module in resultat["modules"].items():
        lignes = [resultat["erreurs"][cle]] if module is None else module["constats"]
        classe = " class='erreur'" if module is None else ""
        parties.append(f"<section class='carte'><header><h2>{e(NOMS[cle])}</h2>"
                       f"<span class='pastille {niveau_points(resultat, cle)}'>{e(points_module(resultat, cle))}</span>"
                       "</header>"
                       + "".join(f"<p{classe}>{e(anonymiser(ligne))}</p>" for ligne in lignes)
                       + (_tableau(COLONNES[cle], lignes_detail(cle, module)) if module else "")
                       + "</section>")
    if "score" in resultat["erreurs"]:
        parties.append(f"<p class='erreur'>{e(anonymiser(resultat['erreurs']['score']))}</p>")
    parties.append("<footer class='discret'>Rapport créé sur ce PC par Bilan santé PC. L'application ne modifie rien "
                   "sans l'accord de l'utilisateur et n'envoie aucune donnée personnelle.</footer>")
    return ("<!doctype html>\n<html lang='fr'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>Bilan santé PC - {resultat['date']:%d/%m/%Y}</title><style>{STYLE_HTML}</style></head>"
            f"<body>{''.join(parties)}</body></html>\n")
