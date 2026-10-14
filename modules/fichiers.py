"""Module fichiers inutiles : taille de la Corbeille et des fichiers temporaires.

Le scan est en lecture seule. Seule exception de toute l'application : vider_corbeille(),
lancée uniquement par le bouton « Vider la Corbeille », après la confirmation de Windows.
"""

import ctypes
import os
import tempfile
from ctypes import wintypes

from modules.disque import taille_dossier, taille_lisible


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


def scan(taille_temporaires: int | None = None) -> dict:
    """Point d'entrée du module (hors score) : renvoie les tailles et les constats.

    `taille_temporaires` : taille déjà mesurée, pour ne remesurer que la Corbeille (après l'avoir vidée) :
    parcourir les fichiers temporaires peut prendre plusieurs secondes.
    """
    lecteur = os.environ.get("SystemDrive", "C:")
    temporaires = tempfile.gettempdir()
    if taille_temporaires is None:
        taille_temporaires = taille_dossier(temporaires)
    taille_corbeille = corbeille()
    # Ce qui libérerait de la place sur le disque de Windows, le seul qui compte dans le score.
    sur_systeme = corbeille(lecteur + os.sep)
    if temporaires.upper().startswith(lecteur.upper()):
        sur_systeme += taille_temporaires
    return {
        "score": None,  # hors score : voir modules/score.conseils_fichiers()
        "constats": [f"Corbeille : {taille_lisible(taille_corbeille)}." if taille_corbeille
                     else "La Corbeille est vide.",
                     f"Fichiers temporaires : {taille_lisible(taille_temporaires)}."],
        "corbeille": taille_corbeille,
        "temporaires": taille_temporaires,
        "recuperable_systeme": sur_systeme,
    }
