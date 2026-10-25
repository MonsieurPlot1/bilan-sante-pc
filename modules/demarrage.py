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
# Où Windows note les programmes désactivés dans Paramètres > Applications > Démarrage.
CLE_APPROUVES = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"

# HKLM existe en deux vues sur Windows 64 bits (programmes 64 et 32 bits).
# Dernier élément : la sous-clé de CLE_APPROUVES qui correspond à la source.
SOURCES_REGISTRE = [
    (winreg.HKEY_CURRENT_USER, 0, "Registre (utilisateur)", "Run"),
    (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY, "Registre (tous les utilisateurs)", "Run"),
    (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY, "Registre (tous les utilisateurs, 32 bits)", "Run32"),
]

DOSSIERS_DEMARRAGE = [
    (r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup", "Dossier Démarrage (utilisateur)",
     winreg.HKEY_CURRENT_USER),
    (r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\Startup", "Dossier Démarrage (tous les utilisateurs)",
     winreg.HKEY_LOCAL_MACHINE),
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


def est_desactive(donnees: object) -> bool:
    """Valeur StartupApproved : premier octet impair = désactivé (02 ou 06 = activé, 03 ou 07 = désactivé).

    Format non documenté par Microsoft, mais stable depuis Windows 8 et repris par les outils de diagnostic.
    """
    return isinstance(donnees, bytes) and bool(donnees) and bool(donnees[0] & 1)


def desactives(racine: int, sous_cle: str) -> set[str]:
    """Noms (en minuscules) des programmes désactivés dans les Paramètres, pour une source."""
    try:
        with winreg.OpenKey(racine, rf"{CLE_APPROUVES}\{sous_cle}", 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as cle:
            valeurs = [winreg.EnumValue(cle, i) for i in range(winreg.QueryInfoKey(cle)[1])]
    except OSError:  # clé absente : rien n'a été désactivé
        return set()
    return {nom.lower() for nom, donnees, _ in valeurs if est_desactive(donnees)}


def lister_programmes() -> list[dict]:
    """Liste les programmes au démarrage : nom, chemin, éditeur, source et s'il est actif."""
    programmes = []
    for racine, vue, source, sous_cle in SOURCES_REGISTRE:
        coupes = desactives(racine, sous_cle)
        for nom, commande in _lire_run(racine, vue):
            chemin = extraire_chemin(commande)
            programmes.append({"nom": nom, "chemin": chemin, "editeur": editeur(chemin), "source": source,
                               "actif": nom.lower() not in coupes})

    for dossier, source, racine in DOSSIERS_DEMARRAGE:
        dossier = Path(os.path.expandvars(dossier))
        if not dossier.is_dir():
            continue
        coupes = desactives(racine, "StartupFolder")  # noms de fichiers, extension comprise
        try:
            contenu = sorted(dossier.iterdir())
        except OSError:  # dossier illisible : les autres sources sont quand même listées
            continue
        for fichier in contenu:
            if not fichier.is_file() or fichier.name.lower() == "desktop.ini":
                continue
            chemin = str(fichier)
            if fichier.suffix.lower() == ".lnk":
                try:
                    chemin = cible_raccourci(fichier.read_bytes()) or chemin
                except OSError:  # raccourci illisible (accès refusé) : on montre le raccourci lui-même
                    pass
            programmes.append({"nom": fichier.stem, "chemin": chemin, "editeur": editeur(chemin), "source": source,
                               "actif": fichier.name.lower() not in coupes})
    return programmes


def scan() -> dict:
    """Point d'entrée du module : renvoie les programmes actifs et les constats.

    Les programmes désactivés dans les Paramètres ne se lancent pas : ils ne comptent pas.
    """
    tous = lister_programmes()
    programmes = [p for p in tous if p["actif"]]
    nb, nb_desactives = len(programmes), len(tous) - len(programmes)
    phrase = f"{nb} programme se lance" if nb <= 1 else f"{nb} programmes se lancent"
    s = "s" if nb_desactives > 1 else ""
    precision = f" ({nb_desactives} autre{s} désactivé{s} dans les Paramètres)" if nb_desactives else ""
    return {
        "score": None,  # calculé ensuite par modules/score.calculer()
        "constats": [f"{phrase} au démarrage de Windows{precision}."],
        "programmes": programmes,
        "nb_desactives": nb_desactives,
    }
