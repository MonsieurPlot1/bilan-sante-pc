"""Module démarrage : liste les programmes lancés au démarrage de Windows.

Lecture seule : on lit le registre et les dossiers Démarrage, on ne modifie rien.
"""

import ctypes
import os
import re
import shutil
import struct
import winreg
from pathlib import Path

CLE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"

# HKLM existe en deux vues sur Windows 64 bits (programmes 64 et 32 bits).
SOURCES_REGISTRE = [
    (winreg.HKEY_CURRENT_USER, 0, "Registre (utilisateur)"),
    (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY, "Registre (tous les utilisateurs)"),
    (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY, "Registre (tous les utilisateurs, 32 bits)"),
]

DOSSIERS_DEMARRAGE = [
    (r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup", "Dossier Démarrage (utilisateur)"),
    (r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\Startup", "Dossier Démarrage (tous les utilisateurs)"),
]


def extraire_chemin(commande: str) -> str:
    """Extrait le chemin de l'exécutable d'une ligne de commande du registre."""
    commande = os.path.expandvars(commande.strip())
    if commande.startswith('"'):
        chemin = commande[1:].split('"', 1)[0]
    else:
        # Chemin sans guillemets pouvant contenir des espaces : on coupe après ".exe".
        trouve = re.match(r"(.+?\.exe)\b", commande, re.IGNORECASE)
        chemin = trouve.group(1) if trouve else commande.split(" ", 1)[0]
    # "rundll32.exe" seul : on cherche le fichier dans le PATH.
    return chemin if os.path.isabs(chemin) else shutil.which(chemin) or chemin


def _chaine(donnees: bytes, debut: int, unicode: bool) -> str:
    """Lit une chaîne terminée par un zéro dans un fichier .lnk."""
    if unicode:
        fin = debut
        while donnees[fin:fin + 2] not in (b"\0\0", b""):
            fin += 2
        return donnees[debut:fin].decode("utf-16-le", "replace")
    fin = donnees.find(b"\0", debut)
    return donnees[debut:fin if fin != -1 else None].decode("mbcs", "replace")


def cible_raccourci(donnees: bytes) -> str | None:
    """Renvoie la cible d'un raccourci .lnk (format MS-SHLLINK), ou None si introuvable."""
    try:
        drapeaux = struct.unpack_from("<I", donnees, 0x14)[0]
        position = 0x4C  # fin de l'en-tête
        if drapeaux & 0x01:  # HasLinkTargetIDList : on saute la liste d'identifiants
            position += 2 + struct.unpack_from("<H", donnees, position)[0]
        if not drapeaux & 0x02:  # pas de HasLinkInfo : cible non exprimée en chemin
            return None
        info = donnees[position:]
        taille_entete, drapeaux_info = struct.unpack_from("<II", info, 4)
        if not drapeaux_info & 0x01:  # pas de chemin local (ex. partage réseau)
            return None
        if taille_entete >= 0x24:
            base, suffixe = struct.unpack_from("<II", info, 28)
            return _chaine(info, base, True) + _chaine(info, suffixe, True)
        base, suffixe = struct.unpack_from("<I4xI", info, 16)  # 4 octets ignorés : chemin réseau
        return _chaine(info, base, False) + _chaine(info, suffixe, False)
    except (struct.error, IndexError):
        return None


def editeur(chemin: str) -> str | None:
    """Renvoie l'éditeur (CompanyName) inscrit dans le fichier, ou None."""
    if not os.path.isfile(chemin):
        return None
    version = ctypes.WinDLL("version")
    taille = version.GetFileVersionInfoSizeW(chemin, None)
    if not taille:
        return None
    tampon = ctypes.create_string_buffer(taille)
    if not version.GetFileVersionInfoW(chemin, 0, taille, tampon):
        return None
    pointeur, longueur = ctypes.c_void_p(), ctypes.c_uint()
    if not version.VerQueryValueW(tampon, r"\VarFileInfo\Translation",
                                  ctypes.byref(pointeur), ctypes.byref(longueur)) or longueur.value < 4:
        return None
    langue, page = struct.unpack("<HH", ctypes.string_at(pointeur.value, 4))
    cle = rf"\StringFileInfo\{langue:04x}{page:04x}\CompanyName"
    if not version.VerQueryValueW(tampon, cle, ctypes.byref(pointeur), ctypes.byref(longueur)) or not longueur.value:
        return None
    # Lecture jusqu'au zéro final : la longueur renvoyée déborde chez certains éditeurs.
    return ctypes.wstring_at(pointeur.value).strip() or None


def _lire_run(racine: int, vue: int) -> list[tuple[str, str]]:
    """Lit les valeurs (nom, commande) d'une clé Run, en lecture seule."""
    try:
        with winreg.OpenKey(racine, CLE_RUN, 0, winreg.KEY_READ | vue) as cle:
            nb_valeurs = winreg.QueryInfoKey(cle)[1]
            valeurs = [winreg.EnumValue(cle, i) for i in range(nb_valeurs)]
    except OSError:  # clé absente ou accès refusé
        return []
    return [(nom, commande) for nom, commande, _ in valeurs if isinstance(commande, str) and commande.strip()]


def lister_programmes() -> list[dict]:
    """Liste les programmes au démarrage : nom, chemin, éditeur et source."""
    programmes = []
    for racine, vue, source in SOURCES_REGISTRE:
        for nom, commande in _lire_run(racine, vue):
            chemin = extraire_chemin(commande)
            programmes.append({"nom": nom, "chemin": chemin, "editeur": editeur(chemin), "source": source})

    for dossier, source in DOSSIERS_DEMARRAGE:
        dossier = Path(os.path.expandvars(dossier))
        if not dossier.is_dir():
            continue
        for fichier in sorted(dossier.iterdir()):
            if not fichier.is_file() or fichier.name.lower() == "desktop.ini":
                continue
            chemin = str(fichier)
            if fichier.suffix.lower() == ".lnk":
                chemin = cible_raccourci(fichier.read_bytes()) or chemin
            programmes.append({"nom": fichier.stem, "chemin": chemin, "editeur": editeur(chemin), "source": source})
    return programmes


def scan() -> dict:
    """Point d'entrée du module : renvoie le score partiel et les constats."""
    programmes = lister_programmes()
    nb = len(programmes)
    phrase = f"{nb} programme se lance" if nb <= 1 else f"{nb} programmes se lancent"
    return {
        "score": None,  # calculé ensuite par modules/score.calculer()
        "constats": [f"{phrase} au démarrage de Windows."],
        "programmes": programmes,
    }
