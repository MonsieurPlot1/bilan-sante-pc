"""Module ressources : mémoire vive, charge du processeur et programmes les plus gourmands.

Lecture seule : on mesure, on ne ferme ni ne modifie aucun programme.
"""

import ctypes
import time
from ctypes import wintypes

import psutil

from modules.disque import taille_lisible

DUREE_MESURE_CPU = 3  # secondes : une mesure instantanée serait trop bruitée
NB_PROCESSUS = 5
SYSTEM_PROCESS_INFORMATION = 5
STATUS_INFO_LENGTH_MISMATCH = 0xC0000004


class _Texte(ctypes.Structure):  # UNICODE_STRING
    _fields_ = [("longueur", wintypes.USHORT), ("maximum", wintypes.USHORT), ("tampon", ctypes.c_void_p)]


class _Processus(ctypes.Structure):  # début de SYSTEM_PROCESS_INFORMATION (winternl.h)
    _fields_ = [("suivant", wintypes.ULONG), ("nb_threads", wintypes.ULONG), ("reserve1", ctypes.c_ubyte * 48),
                ("nom", _Texte), ("priorite", wintypes.LONG), ("pid", ctypes.c_void_p),
                ("reserve2", ctypes.c_void_p), ("handles", wintypes.ULONG), ("session", wintypes.ULONG),
                ("reserve3", ctypes.c_void_p), ("pic_virtuel", ctypes.c_size_t), ("virtuel", ctypes.c_size_t),
                ("reserve4", wintypes.ULONG), ("pic_memoire", ctypes.c_size_t), ("memoire", ctypes.c_size_t)]


def memoire_par_processus() -> list[tuple[str, int]]:
    """(nom, mémoire vive utilisée) de chaque processus, en une seule photo du système.

    psutil interroge chaque processus un par un, et refait une photo complète du système pour
    chaque processus protégé : environ 1 s de processeur au lieu de quelques millisecondes ici.
    """
    ntdll, taille = ctypes.WinDLL("ntdll"), 1 << 20
    while True:
        tampon, necessaire = ctypes.create_string_buffer(taille), wintypes.ULONG()
        statut = ntdll.NtQuerySystemInformation(SYSTEM_PROCESS_INFORMATION, tampon, taille,
                                                ctypes.byref(necessaire)) & 0xFFFFFFFF
        if statut != STATUS_INFO_LENGTH_MISMATCH:
            break
        # Tampon trop petit : on recommence plus grand, avec une marge pour les processus nés entre-temps.
        taille = necessaire.value + 65536
    if statut:
        raise OSError(f"NtQuerySystemInformation : erreur 0x{statut:08X}")
    processus, position = [], 0
    while True:
        info = _Processus.from_buffer(tampon, position)
        nom = ctypes.wstring_at(info.nom.tampon, info.nom.longueur // 2) if info.nom.tampon else ""
        processus.append((nom, info.memoire))
        if not info.suivant:
            return processus
        position += info.suivant


def memoire_installee() -> int | None:
    """Mémoire vive installée sur la carte mère, en octets, ou None si Windows ne la donne pas.

    psutil donne la mémoire utilisable par Windows, un peu plus petite (une partie est réservée au matériel).
    """
    kilo_octets = ctypes.c_ulonglong()
    if not ctypes.WinDLL("kernel32").GetPhysicallyInstalledSystemMemory(ctypes.byref(kilo_octets)):
        return None
    return kilo_octets.value * 1024


def charge_processeur(duree: float) -> float:
    """Charge moyenne du processeur pendant `duree` secondes (en %), sans compter l'application elle-même.

    Les autres parties de l'analyse tournent pendant la mesure (lecture des dossiers) : leur travail n'est pas
    ce qui ralentit le PC d'habitude, il fausserait le chiffre. Même calcul que psutil.cpu_percent(), moins
    le temps de processeur pris par l'application.
    """
    application = psutil.Process()
    avant, avant_application = psutil.cpu_times(), application.cpu_times()
    time.sleep(duree)
    apres, apres_application = psutil.cpu_times(), application.cpu_times()
    total = sum(apres) - sum(avant)
    if total <= 0:
        return 0.0
    occupe = total - (apres.idle - avant.idle)
    application_seule = (apres_application.user + apres_application.system
                         - avant_application.user - avant_application.system)
    return max(0.0, min(100.0, 100 * (occupe - application_seule) / total))


def plus_gourmands(processus: list[tuple[str, int]], nombre: int = NB_PROCESSUS) -> list[dict]:
    """Les `nombre` programmes qui occupent le plus de mémoire, regroupés par nom.

    Regroupés : un navigateur lance des dizaines de processus du même nom,
    les lister un par un ne dirait rien d'utile.
    """
    totaux: dict[str, int] = {}
    for nom, octets in processus:
        if not nom:  # processus inactif du système, sans nom
            continue
        totaux[nom] = totaux.get(nom, 0) + octets
    tries = sorted(totaux.items(), key=lambda element: element[1], reverse=True)[:nombre]
    return [{"nom": nom, "octets": octets} for nom, octets in tries]


def scan() -> dict:
    """Point d'entrée du module : renvoie les mesures et les constats."""
    memoire = psutil.virtual_memory()
    cpu = charge_processeur(DUREE_MESURE_CPU)
    ram = {"total": memoire.total, "utilise": memoire.total - memoire.available, "pourcentage": memoire.percent}
    installee = memoire_installee()
    constats = [f"Mémoire vive : {taille_lisible(ram['utilise'])} utilisés sur "
                f"{taille_lisible(ram['total'])} ({ram['pourcentage']:.0f} %)."]
    if installee:
        constats.append(f"Mémoire vive installée : {installee / 1024**3:.0f} Go.")
    constats.append(f"Processeur : occupé à {cpu:.0f} % en moyenne pendant {DUREE_MESURE_CPU} secondes.")
    return {
        "score": None,  # calculé ensuite par modules/score.calculer()
        "constats": constats,
        "ram": ram,
        "installee": installee,
        "cpu": cpu,
        "processus": plus_gourmands(memoire_par_processus()),
    }
