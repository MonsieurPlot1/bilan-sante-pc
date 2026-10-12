"""Calcul du score /100 et des conseils à partir des résultats des modules (calcul v2).

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

IMPACT_MIN = 1  # un conseil qui ferait regagner moins d'un point n'est pas affiché


def lineaire(valeur: float, ok: float, zero: float) -> float:
    """1 jusqu'au seuil `ok`, puis baisse régulière jusqu'à 0 au seuil `zero`."""
    if valeur <= ok:
        return 1.0
    if valeur >= zero:
        return 0.0
    return (zero - valeur) / (zero - ok)


def disque_systeme(disques: list[dict]) -> dict | None:
    """Renvoie le disque où Windows est installé (C: en général), ou None."""
    lecteur = os.environ.get("SystemDrive", "C:").upper()
    return next((d for d in disques if d["disque"].upper().startswith(lecteur)), None)


# --- Santé de chaque module, de 0 (mauvais) à 1 (parfait) ---

def sante_demarrage(resultat: dict) -> float:
    return lineaire(len(resultat["programmes"]), config.DEMARRAGE_NB_OK, config.DEMARRAGE_NB_ZERO)


def sante_disque(resultat: dict) -> float:
    systeme = disque_systeme(resultat["disques"])
    # Disque système introuvable : on ne peut pas juger, on ne pénalise pas.
    return lineaire(systeme["pourcentage"], config.DISQUE_SEUIL_OK, config.DISQUE_SEUIL_ZERO) if systeme else 1.0


def sante_ram(resultat: dict) -> float:
    return lineaire(resultat["ram"]["pourcentage"], config.RAM_SEUIL_OK, config.RAM_SEUIL_ZERO)


def sante_cpu(resultat: dict) -> float:
    return lineaire(resultat["cpu"], config.CPU_SEUIL_OK, config.CPU_SEUIL_ZERO)


def sante_ressources(resultat: dict) -> float:
    return (sante_ram(resultat) + sante_cpu(resultat)) / 2


def sante_batterie(resultat: dict) -> float:
    usure = (1 - resultat["sante"]) * 100
    return lineaire(usure, config.BATTERIE_USURE_OK, config.BATTERIE_USURE_ZERO)


# --- Conseils : (points qu'ils peuvent faire regagner, texte) ---

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


def conseil_ram(resultat: dict) -> str:
    noms = ", ".join(f"{Path(p['nom']).stem} ({taille_lisible(p['octets'])})" for p in resultat["processus"][:3])
    return (f"La mémoire vive est utilisée à {resultat['ram']['pourcentage']:.0f} % : quand elle est pleine, "
            "tout ralentit. " + (f"Ceux qui en prennent le plus en ce moment : {noms}. " if noms else "")
            + "Fermer les programmes et les onglets dont vous ne vous servez pas libère de la mémoire. "
            "Attention : certains doivent rester ouverts (antivirus, programmes de Windows). "
            "En cas de doute, laissez-les. Si c'est toujours le cas, ajouter de la mémoire au PC peut aider.")


def conseil_cpu(cpu: float) -> str:
    return (f"Le processeur était occupé à {cpu:.0f} % pendant la mesure : un programme travaille peut-être "
            "en arrière-plan. Le Gestionnaire des tâches (Ctrl + Maj + Échap) montre lequel. "
            "Une mise à jour de Windows ou une analyse de l'antivirus, c'est normal : laissez-les finir.")


def conseil_batterie(sante: float) -> str:
    return (f"La batterie ne garde plus que {sante * 100:.0f} % de sa capacité d'origine : c'est l'usure "
            "normale avec le temps, et c'est pour ça que l'autonomie baisse. Si cela vous gêne, "
            "un réparateur peut la remplacer.")


def conseils_demarrage(resultat: dict, points: int) -> list[tuple[float, str]]:
    return [(points * (1 - sante_demarrage(resultat)), conseil_demarrage(len(resultat["programmes"])))]


def conseils_disque(resultat: dict, points: int) -> list[tuple[float, str]]:
    systeme = disque_systeme(resultat["disques"])
    if not systeme:
        return []
    impact = points * (1 - sante_disque(resultat))
    conseils = [(impact, conseil_disque(systeme))]
    if dossier := conseil_dossier(resultat["gros_dossiers"]):
        conseils.append((impact, dossier))  # tri stable : reste après le conseil disque
    return conseils


def conseils_ressources(resultat: dict, points: int) -> list[tuple[float, str]]:
    # RAM et processeur comptent chacun pour la moitié des points du module.
    return [(points / 2 * (1 - sante_ram(resultat)), conseil_ram(resultat)),
            (points / 2 * (1 - sante_cpu(resultat)), conseil_cpu(resultat["cpu"]))]


def conseils_batterie(resultat: dict, points: int) -> list[tuple[float, str]]:
    return [(points * (1 - sante_batterie(resultat)), conseil_batterie(resultat["sante"]))]


MODULES = {
    "demarrage": (sante_demarrage, conseils_demarrage),
    "disque": (sante_disque, conseils_disque),
    "ressources": (sante_ressources, conseils_ressources),
    "batterie": (sante_batterie, conseils_batterie),
}


def bareme(resultats: dict[str, dict | None]) -> dict[str, int]:
    """Points de chaque module : la batterie compte si elle est là et que son usure est mesurable."""
    if "batterie" not in resultats:
        return config.POINTS_SANS_BATTERIE
    batterie = resultats["batterie"]
    if batterie is None:  # module en erreur : on ne sait pas, le score global sera incomplet
        return config.POINTS_AVEC_BATTERIE
    mesurable = batterie.get("applicable", True) and batterie.get("sante") is not None
    return config.POINTS_AVEC_BATTERIE if mesurable else config.POINTS_SANS_BATTERIE


def calculer(resultats: dict[str, dict | None]) -> dict:
    """Score global /100, score par module et conseils (les plus utiles d'abord).

    `resultats` : résultat de chaque module, None pour un module en erreur.
    Si un module manque ou est en erreur, le score global vaut None (il serait trompeur).
    """
    points = bareme(resultats)
    scores, conseils = {}, []
    for cle, maximum in points.items():
        if resultats.get(cle) is None:
            continue
        sante, conseils_module = MODULES[cle]
        scores[cle] = round(sante(resultats[cle]) * maximum)
        conseils += [c for c in conseils_module(resultats[cle], maximum) if c[0] >= IMPACT_MIN]
    conseils.sort(key=lambda conseil: conseil[0], reverse=True)

    return {
        "score": sum(scores.values()) if len(scores) == len(points) else None,
        "scores": scores,
        "bareme": points,
        "conseils": [texte for _, texte in conseils[:config.NB_CONSEILS_MAX]],
        "version": config.SCORE_VERSION,
    }
