"""Module disque : espace des disques et plus gros dossiers du profil utilisateur.

Lecture seule : on mesure les tailles, on ne supprime ni ne déplace rien.
"""

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

import psutil

NB_GROS_DOSSIERS = 10
OPEN_EXISTING = 3
IOCTL_STORAGE_QUERY_PROPERTY = 0x2D1400
PROPRIETE_PENALITE = 7  # StorageDeviceSeekPenaltyProperty : vraie pour un disque à plateaux (HDD)


class _Requete(ctypes.Structure):  # STORAGE_PROPERTY_QUERY
    _fields_ = [("propriete", ctypes.c_int), ("type", ctypes.c_int), ("extra", ctypes.c_ubyte * 1)]


class _Penalite(ctypes.Structure):  # DEVICE_SEEK_PENALTY_DESCRIPTOR
    _fields_ = [("version", wintypes.DWORD), ("taille", wintypes.DWORD), ("penalite", wintypes.BOOLEAN)]


def disque_dur(lecteur: str) -> bool | None:
    """Vrai si `lecteur` (ex. « C: ») est un disque dur à plateaux (HDD), faux pour un SSD, None si inconnu.

    Le volume est ouvert sans aucun droit d'accès : on interroge seulement le pilote, sans lire ni écrire.
    """
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                     wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                         ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    poignee = kernel32.CreateFileW("\\\\.\\" + lecteur.rstrip("\\"), 0, 3, None, OPEN_EXISTING, 0, None)
    if poignee in (None, wintypes.HANDLE(-1).value):
        return None
    try:
        requete, reponse, lus = _Requete(propriete=PROPRIETE_PENALITE), _Penalite(), wintypes.DWORD()
        if not kernel32.DeviceIoControl(poignee, IOCTL_STORAGE_QUERY_PROPERTY, ctypes.byref(requete),
                                        ctypes.sizeof(requete), ctypes.byref(reponse), ctypes.sizeof(reponse),
                                        ctypes.byref(lus), None):
            return None  # ex. volume réparti sur plusieurs disques
        return bool(reponse.penalite)
    finally:
        kernel32.CloseHandle(poignee)


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
    constats = [f"Disque {d['disque'].rstrip(os.sep)} {taille_lisible(d['libre'])} libres sur "
                f"{taille_lisible(d['total'])} ({d['pourcentage']:.0f} % utilisé)." for d in disques]
    hdd = disque_dur(os.environ.get("SystemDrive", "C:"))
    if hdd is not None:
        constats.append("Windows est installé sur un disque dur classique (HDD)." if hdd
                        else "Windows est installé sur un SSD (disque rapide).")
    return {
        "score": None,  # calculé ensuite par modules/score.calculer()
        "constats": constats,
        "disques": disques,
        "systeme_hdd": hdd,
        # Path.home() = C:\Users\<utilisateur>, le profil est sur C: dans une installation standard.
        "gros_dossiers": gros_dossiers(Path.home()),
    }
