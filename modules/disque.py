"""Module disque : espace des disques et plus gros dossiers du profil utilisateur.

Lecture seule : on mesure les tailles, on ne supprime ni ne déplace rien.
"""

import os
from pathlib import Path

import psutil

NB_GROS_DOSSIERS = 10


def taille_lisible(octets: int) -> str:
    """Convertit des octets en texte lisible, comme l'Explorateur (ex. « 12,3 Go »)."""
    for unite in ("octets", "Ko", "Mo", "Go"):
        if octets < 1024:
            break
        octets /= 1024
    else:
        unite = "To"
    return f"{octets:.0f} {unite}" if unite == "octets" else f"{octets:.1f} {unite}".replace(".", ",")


def lister_disques() -> list[dict]:
    """Espace total, utilisé, libre et pourcentage utilisé de chaque disque."""
    disques = []
    for partition in psutil.disk_partitions():
        if "cdrom" in partition.opts or not partition.fstype:  # lecteur vide ou CD
            continue
        try:
            usage = psutil.disk_usage(partition.mountpoint)
        except OSError:  # disque non prêt ou accès refusé
            continue
        disques.append({"disque": partition.mountpoint, "total": usage.total, "utilise": usage.used,
                        "libre": usage.free, "pourcentage": usage.percent})
    return disques


def taille_dossier(dossier: str) -> int:
    """Taille totale d'un dossier en octets, en ignorant les éléments inaccessibles."""
    total, a_visiter = 0, [dossier]
    while a_visiter:
        try:
            with os.scandir(a_visiter.pop()) as entrees:
                for entree in entrees:
                    try:
                        # Jonctions et liens ignorés : ils pointent ailleurs (voire sur eux-mêmes).
                        if entree.is_symlink() or entree.is_junction():
                            continue
                        if entree.is_dir():
                            a_visiter.append(entree.path)
                        else:
                            total += entree.stat().st_size
                    except OSError:
                        continue
        except OSError:  # dossier protégé : on passe
            continue
    return total


def gros_dossiers(racine: Path, nombre: int = NB_GROS_DOSSIERS) -> list[dict]:
    """Les `nombre` plus gros dossiers de premier niveau de `racine`, du plus gros au plus petit."""
    try:
        dossiers = [d for d in racine.iterdir() if d.is_dir() and not d.is_symlink() and not d.is_junction()]
    except OSError:
        return []
    tailles = [{"chemin": str(d), "taille": taille_dossier(str(d))} for d in dossiers]
    return sorted(tailles, key=lambda d: d["taille"], reverse=True)[:nombre]


def scan() -> dict:
    """Point d'entrée du module : renvoie le score partiel et les constats."""
    disques = lister_disques()
    return {
        "score": None,  # calculé ensuite par modules/score.calculer()
        "constats": [f"Disque {d['disque']} : {taille_lisible(d['libre'])} libres sur "
                     f"{taille_lisible(d['total'])} ({d['pourcentage']:.0f} % utilisé)." for d in disques],
        "disques": disques,
        # Path.home() = C:\Users\<utilisateur>, le profil est sur C: dans une installation standard.
        "gros_dossiers": gros_dossiers(Path.home()),
    }
