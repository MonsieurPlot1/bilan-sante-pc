"""Module fichiers inutiles : taille de la Corbeille, des fichiers temporaires, du cache des navigateurs
et de l'ancienne version de Windows (Windows.old).

Le scan est en lecture seule. Seules exceptions de toute l'application, uniquement sur clic :
vider_corbeille(), lancée par le bouton « Vider la Corbeille » après la confirmation de Windows, et
mettre_a_la_corbeille(), lancée par un bouton « Supprimer » de l'onglet Stockage après confirmation.
"""

import ctypes
import os
import tempfile
from ctypes import wintypes
from pathlib import Path

from modules.disque import taille_dossier, taille_lisible

# Dossiers de cache sous %LOCALAPPDATA% (« * » : un dossier par profil). Ce que le navigateur
# efface avec « Images et fichiers en cache », sans toucher aux mots de passe ni à l'historique.
CACHES_NAVIGATEURS = {
    "Chrome": ["Google/Chrome/User Data/*/Cache", "Google/Chrome/User Data/*/Code Cache"],
    "Edge": ["Microsoft/Edge/User Data/*/Cache", "Microsoft/Edge/User Data/*/Code Cache"],
    "Firefox": ["Mozilla/Firefox/Profiles/*/cache2"],
}


class _InfoCorbeille(ctypes.Structure):  # SHQUERYRBINFO
    _pack_ = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 1  # alignement de shellapi.h
    _fields_ = [("cbSize", wintypes.DWORD), ("taille", ctypes.c_longlong), ("nombre", ctypes.c_longlong)]


def corbeille(racine: str | None = None) -> int:
    """Taille de la Corbeille en octets : celle du disque `racine` (ex. « C:\\ »), ou de tous les disques."""
    shell32 = ctypes.WinDLL("shell32")
    shell32.SHQueryRecycleBinW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p]
    shell32.SHQueryRecycleBinW.restype = ctypes.c_long
    info = _InfoCorbeille(cbSize=ctypes.sizeof(_InfoCorbeille))
    erreur = shell32.SHQueryRecycleBinW(racine, ctypes.byref(info))
    if erreur:
        raise OSError(f"SHQueryRecycleBinW : erreur 0x{erreur & 0xFFFFFFFF:08X}")
    return info.taille


def vider_corbeille(fenetre: int = 0) -> None:
    """Vide la Corbeille de tous les disques, après la demande de confirmation de Windows.

    Aucun drapeau : Windows affiche sa confirmation, sa progression et son son habituels. Si
    l'utilisateur refuse, rien n'est supprimé ; l'appelant le constate en remesurant la Corbeille.
    `fenetre` : identifiant de la fenêtre parente, pour que la confirmation s'affiche par-dessus.
    """
    shell32 = ctypes.WinDLL("shell32")
    shell32.SHEmptyRecycleBinW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.DWORD]
    shell32.SHEmptyRecycleBinW.restype = ctypes.c_long
    shell32.SHEmptyRecycleBinW(fenetre, None, 0)


# SHFileOperationW : suppression vers la Corbeille.
FO_DELETE = 3
FOF_NOCONFIRMATION = 0x10  # l'application a déjà demandé confirmation
FOF_ALLOWUNDO = 0x40  # à la Corbeille, récupérable
FOF_WANTNUKEWARNING = 0x4000  # Windows prévient avant de supprimer pour de bon ce qui n'y tient pas


class _OperationFichiers(ctypes.Structure):  # SHFILEOPSTRUCTW
    _pack_ = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 1  # alignement de shellapi.h
    _fields_ = [("fenetre", wintypes.HWND), ("operation", wintypes.UINT), ("depuis", ctypes.c_void_p),
                ("vers", ctypes.c_void_p), ("options", wintypes.WORD), ("annule", wintypes.BOOL),
                ("correspondances", ctypes.c_void_p), ("titre", wintypes.LPCWSTR)]


def mettre_a_la_corbeille(chemin: str, fenetre: int = 0) -> None:
    """Met un fichier ou un dossier à la Corbeille, d'où il reste récupérable tant qu'elle n'est pas vidée.

    Windows montre sa progression et ses erreurs (fichier ouvert dans un programme…), et demande avant
    de supprimer pour de bon ce qui ne tient pas dans la Corbeille. L'appelant vérifie ensuite ce qui a
    vraiment disparu. `fenetre` : identifiant de la fenêtre parente, pour que Windows s'affiche par-dessus.
    """
    # Un seul élément, désigné en entier : pas de chemin relatif, pas de joker, pas la racine d'un disque.
    if not os.path.isabs(chemin) or any(c in chemin for c in "*?") or os.path.dirname(chemin) == chemin:
        raise ValueError(f"Chemin refusé : {chemin!r}")
    liste = ctypes.create_unicode_buffer(chemin + "\0")  # liste de chemins terminée par deux zéros
    operation = _OperationFichiers(fenetre=fenetre, operation=FO_DELETE, depuis=ctypes.addressof(liste),
                                   options=FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_WANTNUKEWARNING)
    shell32 = ctypes.WinDLL("shell32")
    shell32.SHFileOperationW.argtypes = [ctypes.c_void_p]
    shell32.SHFileOperationW.restype = ctypes.c_int
    shell32.SHFileOperationW(ctypes.byref(operation))


def dossier_local() -> Path:
    """%LOCALAPPDATA%, où les navigateurs rangent leur cache."""
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))


def caches_navigateurs() -> dict[str, int]:
    """Taille du cache de chaque navigateur présent (tous profils confondus), en octets."""
    tailles = {}
    for navigateur, motifs in CACHES_NAVIGATEURS.items():
        dossiers = [d for motif in motifs for d in dossier_local().glob(motif) if d.is_dir()]
        if dossiers:
            tailles[navigateur] = sum(taille_dossier(str(d)) for d in dossiers)
    return tailles


def scan(precedent: dict | None = None) -> dict:
    """Point d'entrée du module (hors score) : renvoie les tailles et les constats.

    `precedent` : résultat d'une analyse précédente, pour ne remesurer que la Corbeille (après l'avoir
    vidée) : parcourir les fichiers temporaires, les caches et Windows.old peut prendre plusieurs secondes.
    """
    lecteur = os.environ.get("SystemDrive", "C:").upper()
    temporaires = tempfile.gettempdir()
    taille_temporaires = precedent["temporaires"] if precedent else taille_dossier(temporaires)
    navigateurs = precedent["navigateurs"] if precedent else caches_navigateurs()
    # Gardée après une grosse mise à jour de Windows ; 0 si le dossier n'existe pas.
    # shortcut: les fichiers à plusieurs liens (WinSxS) comptent une fois par lien, d'où « environ » ;
    # passer par os.stat (st_nlink) si l'écart avec les Paramètres gêne.
    ancien_windows = precedent["ancien_windows"] if precedent else taille_dossier(lecteur + os.sep + "Windows.old")
    taille_corbeille = corbeille()
    # Ce qui libérerait de la place sur le disque de Windows, le seul qui compte dans le score.
    sur_systeme = corbeille(lecteur + os.sep) + ancien_windows
    if temporaires.upper().startswith(lecteur):
        sur_systeme += taille_temporaires
    if str(dossier_local()).upper().startswith(lecteur):
        sur_systeme += sum(navigateurs.values())
    constats = [f"Corbeille : {taille_lisible(taille_corbeille)}." if taille_corbeille else "La Corbeille est vide.",
                f"Fichiers temporaires : {taille_lisible(taille_temporaires)}."]
    if navigateurs:
        detail = ", ".join(f"{nom} {taille_lisible(taille)}" for nom, taille in navigateurs.items())
        constats.append(f"Cache des navigateurs : {taille_lisible(sum(navigateurs.values()))} ({detail}).")
    if ancien_windows:
        constats.append(f"Ancienne version de Windows (Windows.old) : environ {taille_lisible(ancien_windows)}.")
    return {
        "score": None,  # hors score : voir modules/score.conseils_fichiers()
        "constats": constats,
        "corbeille": taille_corbeille,
        "temporaires": taille_temporaires,
        "navigateurs": navigateurs,
        "ancien_windows": ancien_windows,
        "recuperable_systeme": sur_systeme,
    }
