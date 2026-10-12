"""Calcul du score /100 et des conseils à partir des résultats des modules.

Lecture seule : on ne fait que lire les résultats déjà collectés.
"""

import os
from pathlib import Path

import config
from modules.disque import taille_lisible

# Dossiers personnels qu'on peut conseiller de trier (noms affichés en français).
# AppData et les dossiers techniques sont exclus : y faire le ménage à la main est risqué.
DOSSIERS_A_TRIER = {
    "downloads": "Téléchargements",
    "desktop": "Bureau",
    "documents": "Documents",
    "videos": "Vidéos",
    "pictures": "Images",
    "music": "Musique",
}


def points_disque(pourcentage: float) -> int:
    """Points du disque : plein jusqu'au seuil OK, puis baisse linéaire jusqu'à 0."""
    if pourcentage <= config.DISQUE_SEUIL_OK:
        return config.POINTS_DISQUE
    if pourcentage >= config.DISQUE_SEUIL_ZERO:
        return 0
    reste = (config.DISQUE_SEUIL_ZERO - pourcentage) / (config.DISQUE_SEUIL_ZERO - config.DISQUE_SEUIL_OK)
    return round(config.POINTS_DISQUE * reste)


def points_demarrage(nb_programmes: int) -> int:
    """Points du démarrage : pénalité par programme au-delà du seuil, plancher 0."""
    en_trop = max(0, nb_programmes - config.DEMARRAGE_NB_OK)
    return max(0, config.POINTS_DEMARRAGE - config.DEMARRAGE_PENALITE * en_trop)


def disque_systeme(disques: list[dict]) -> dict | None:
    """Renvoie le disque où Windows est installé (C: en général), ou None."""
    lecteur = os.environ.get("SystemDrive", "C:").upper()
    return next((d for d in disques if d["disque"].upper().startswith(lecteur)), None)


def conseil_demarrage(nb_programmes: int) -> str:
    return (f"{nb_programmes} programmes se lancent en même temps que Windows : c'est beaucoup, "
            "et ça ralentit l'allumage du PC. Dans Paramètres > Applications > Démarrage, "
            "vous pouvez couper ceux dont vous n'avez pas besoin dès l'allumage. "
            "Attention : certains sont utiles (antivirus, pilotes de la carte graphique, du son, "
            "de la souris ou du clavier). En cas de doute, laissez-les.")


def conseil_disque(disque: dict) -> str:
    return (f"Votre disque {disque['disque'].rstrip(os.sep)} est plein à {disque['pourcentage']:.0f} % "
            f"(il reste {taille_lisible(disque['libre'])}). Un disque presque plein ralentit Windows. "
            "Videz la Corbeille et lancez Paramètres > Système > Stockage > Recommandations de nettoyage.")


def conseil_dossier(dossiers: list[dict]) -> str | None:
    """Conseille de trier le plus gros dossier personnel, s'il dépasse le seuil."""
    for dossier in dossiers:  # déjà triés du plus gros au plus petit
        nom = DOSSIERS_A_TRIER.get(Path(dossier["chemin"]).name.lower())
        if nom and dossier["taille"] >= config.GROS_DOSSIER_SEUIL:
            return (f"Votre dossier « {nom} » occupe {taille_lisible(dossier['taille'])}. "
                    "Triez-le : il contient souvent de vieux fichiers oubliés. "
                    "Pensez à sauvegarder ce que vous voulez garder avant d'effacer quoi que ce soit.")
    return None


def calculer(resultats_demarrage: dict, resultats_disque: dict) -> dict:
    """Score global /100, score par module et conseils (les plus utiles d'abord)."""
    nb_programmes = len(resultats_demarrage["programmes"])
    score_demarrage = points_demarrage(nb_programmes)

    systeme = disque_systeme(resultats_disque["disques"])
    # Disque système introuvable : on ne peut pas juger, on ne pénalise pas.
    score_disque = points_disque(systeme["pourcentage"]) if systeme else config.POINTS_DISQUE

    # Chaque conseil est rangé selon les points qu'il peut faire regagner.
    conseils = []
    perte_demarrage = config.POINTS_DEMARRAGE - score_demarrage
    perte_disque = config.POINTS_DISQUE - score_disque
    if perte_demarrage:
        conseils.append((perte_demarrage, conseil_demarrage(nb_programmes)))
    if perte_disque:
        conseils.append((perte_disque, conseil_disque(systeme)))
        if dossier := conseil_dossier(resultats_disque["gros_dossiers"]):
            conseils.append((perte_disque, dossier))  # tri stable : reste après le conseil disque
    conseils.sort(key=lambda conseil: conseil[0], reverse=True)

    return {
        "score": score_demarrage + score_disque,
        "scores": {"demarrage": score_demarrage, "disque": score_disque},
        "conseils": [texte for _, texte in conseils[:config.NB_CONSEILS_MAX]],
    }
