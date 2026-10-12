"""Module ressources : mémoire vive, charge du processeur et programmes les plus gourmands.

Lecture seule : on mesure, on ne ferme ni ne modifie aucun programme.
"""

import psutil

from modules.disque import taille_lisible

DUREE_MESURE_CPU = 3  # secondes : une mesure instantanée serait trop bruitée
NB_PROCESSUS = 5


def plus_gourmands(processus, nombre: int = NB_PROCESSUS) -> list[dict]:
    """Les `nombre` programmes qui occupent le plus de mémoire, regroupés par nom.

    Regroupés : un navigateur lance des dizaines de processus du même nom,
    les lister un par un ne dirait rien d'utile.
    """
    totaux: dict[str, int] = {}
    for proc in processus:
        # process_iter(attrs) saute les processus disparus (NoSuchProcess) et met None
        # quand l'accès est refusé (AccessDenied) : on ignore ces derniers.
        nom, memoire = proc.info.get("name"), proc.info.get("memory_info")
        if not nom or memoire is None:
            continue
        totaux[nom] = totaux.get(nom, 0) + memoire.rss
    tries = sorted(totaux.items(), key=lambda element: element[1], reverse=True)[:nombre]
    return [{"nom": nom, "octets": octets} for nom, octets in tries]


def scan() -> dict:
    """Point d'entrée du module : renvoie les mesures et les constats."""
    memoire = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=DUREE_MESURE_CPU)
    ram = {"total": memoire.total, "utilise": memoire.total - memoire.available, "pourcentage": memoire.percent}
    return {
        "score": None,  # calculé ensuite par modules/score.calculer()
        "constats": [f"Mémoire vive : {taille_lisible(ram['utilise'])} utilisés sur "
                     f"{taille_lisible(ram['total'])} ({ram['pourcentage']:.0f} %).",
                     f"Processeur : occupé à {cpu:.0f} % en moyenne pendant {DUREE_MESURE_CPU} secondes."],
        "ram": ram,
        "cpu": cpu,
        "processus": plus_gourmands(psutil.process_iter(["name", "memory_info"])),
    }
