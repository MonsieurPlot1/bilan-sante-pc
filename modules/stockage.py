"""Module stockage : ce qui occupe un disque, classé en 12 catégories (Système, Applications, Jeux…).

Lecture seule : on additionne les tailles lues dans les dossiers, sans ouvrir ni modifier aucun fichier.
Hors du bilan de santé : parcourir tout un disque prend du temps, il a donc sa propre page.

Un fichier est classé d'abord selon son emplacement (dossier d'un jeu, d'un logiciel, cache…), puis,
s'il n'est dans aucun emplacement connu, selon son extension : une vidéo d'un jeu compte dans Jeux.
« Système » n'est pas parcouru : c'est l'espace utilisé du disque moins tout le reste (Windows,
points de restauration, fichiers que l'application n'a pas le droit de lire).

Seule action, sur un clic « Supprimer » de la page : supprimable() dit quels éléments peuvent être
supprimés définitivement (modules.fichiers.supprimer), retirer() met ensuite l'analyse à jour.
"""

import ctypes
import heapq
import os
import re
import stat
import tempfile
import time
import winreg
from ctypes import wintypes
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Callable

import psutil

from modules.disque import taille_lisible
from modules.fichiers import corbeille, dossier_local
from modules.score import DOSSIERS_A_TRIER, Lien

# (clé, nom, explication), dans l'ordre de la liste quand rien n'est encore mesuré.
CATEGORIES = [
    ("systeme", "Système", "Windows, la mémoire virtuelle et les fichiers protégés que l'application n'a pas "
                           "le droit de lire (comme les applications du Microsoft Store). Indispensable : "
                           "n'y touche pas à la main."),
    ("applications", "Applications", "Les logiciels installés et leurs données."),
    ("jeux", "Jeux", "Steam, Epic, Minecraft et les autres jeux, avec leurs sauvegardes de partie."),
    ("videos", "Vidéos", "Films et vidéos (.mp4, .mkv, .mov…)."),
    ("photos", "Photos", "Photos et images (.jpg, .png, .heic…)."),
    ("musique", "Musique", "Musique et sons (.mp3, .flac, .wav…)."),
    ("documents", "Documents", "PDF, Word, Excel, PowerPoint et fichiers texte."),
    ("archives", "Archives", "Fichiers ZIP, RAR et installateurs (.exe, .msi), souvent oubliés dans "
                             "Téléchargements."),
    ("temporaires", "Fichiers temporaires", "Caches et fichiers temporaires : Windows sait les supprimer "
                                            "sans risque."),
    ("corbeille", "Corbeille", "Les fichiers supprimés, encore récupérables tant que la Corbeille n'est pas vidée."),
    ("sauvegardes", "Sauvegardes", "L'ancienne version de Windows et les sauvegardes de téléphone."),
    ("autres", "Autres", "Tout le reste."),
]
NOMS = {cle: nom for cle, nom, _ in CATEGORIES}

# Où agir pour une catégorie : ça ouvre seulement la page ou le dossier, sans rien modifier.
LIEN_APPLICATIONS: Lien = ("Ouvrir Applications installées", "ms-settings:appsfeatures")
LIEN_STOCKAGE: Lien = ("Ouvrir les Paramètres de stockage", "ms-settings:storagesense")
LIENS: dict[str, Lien] = {
    "applications": LIEN_APPLICATIONS, "jeux": LIEN_APPLICATIONS, "temporaires": LIEN_STOCKAGE,
    "sauvegardes": LIEN_STOCKAGE, "corbeille": ("Ouvrir la Corbeille", "shell:RecycleBinFolder"),
    "archives": ("Ouvrir Téléchargements", str(Path.home() / "Downloads")),
}

# Classement par extension, pour les fichiers rangés hors des emplacements connus.
EXTENSIONS = {
    "videos": ".mp4 .mkv .avi .mov .wmv .webm .m4v .flv .mpg .mpeg .m2ts .mts .3gp .vob",
    "photos": ".jpg .jpeg .jfif .png .gif .bmp .tif .tiff .webp .heic .heif .avif .raw .cr2 .cr3 .nef .arw "
              ".dng .orf .rw2 .psd",
    "musique": ".mp3 .flac .wav .aac .m4a .ogg .oga .wma .opus .aif .aiff .mid .midi",
    "documents": ".pdf .doc .docx .odt .rtf .txt .md .xls .xlsx .xlsm .ods .csv .ppt .pptx .odp .epub .one .pub",
    "archives": ".zip .rar .7z .tar .gz .tgz .bz2 .xz .zst .cab .iso .img .exe .msi .msix .msixbundle .appx "
                ".appxbundle .apk",
    "temporaires": ".tmp .temp .dmp .crdownload .partial",
    "sauvegardes": ".bak",
}
CATEGORIE_EXTENSION = {extension: cle for cle, liste in EXTENSIONS.items() for extension in liste.split()}

# Fichiers de Windows à la racine du disque, montrés à part dans Système (souvent plusieurs Go).
FICHIERS_SYSTEME = {"pagefile.sys": "Mémoire virtuelle (pagefile.sys)",
                    "hiberfil.sys": "Mise en veille prolongée (hiberfil.sys)",
                    "swapfile.sys": "Fichier d'échange (swapfile.sys)"}

# Attributs Windows d'un fichier (st_file_attributes).
SUR_INTERNET = 0x1000 | 0x40000 | 0x400000  # OFFLINE, RECALL_ON_OPEN, RECALL_ON_DATA_ACCESS : OneDrive « en ligne »
REDUIT = 0x200 | 0x800  # SPARSE_FILE, COMPRESSED : la place prise est plus petite que la taille du fichier
FICHIER_SYSTEME = 0x4  # SYSTEM : fichier de Windows (registre du profil, desktop.ini…)

RESTE_WINDOWS = "Windows et fichiers protégés"  # Système, sans les fichiers de Windows mesurés à part

NB_ELEMENTS = 12  # éléments montrés par catégorie
NB_DOSSIERS = 3   # dossiers « Surtout dans » des catégories classées par extension
PAR_EXTENSION = ("videos", "photos", "musique", "documents", "archives", "autres")  # sans emplacement à elles
INTERVALLE_PROGRESSION = 0.1  # secondes entre deux nouvelles de la progression


@dataclass(frozen=True)
class Regle:
    """Emplacement reconnu : tout ce qu'il contient va dans `categorie` (None : pas parcouru, compté
    dans Système par différence).

    `profondeur` : niveau des éléments montrés (0 : ce dossier, 1 : chacun de ses sous-dossiers,
    ex. chaque logiciel de Program Files, 2 : un niveau plus bas, ex. chaque jeu de steamapps\\common).
    `dans` : catégories du dossier parent où la règle s'applique : un dossier « Steam » range un jeu,
    mais pas dans l'ancienne version de Windows ; « Cache » n'est un cache que hors des jeux.
    """
    categorie: str | None
    profondeur: int = 0
    dans: frozenset = frozenset({None, "applications"})


HORS_CLASSEMENT = frozenset({None})
PARTOUT_SAUF_COPIES = frozenset({None, "applications", "jeux"})

# Règles selon le nom d'un dossier (en minuscules), où qu'il soit.
REGLES_NOMS = {
    "program files": Regle("applications", 1, HORS_CLASSEMENT),
    "program files (x86)": Regle("applications", 1, HORS_CLASSEMENT),
    "programdata": Regle("applications", 1, HORS_CLASSEMENT),
    "appdata": Regle("applications", 2, HORS_CLASSEMENT),
    "steam": Regle("jeux"),
    "steamlibrary": Regle("jeux"),
    "steamapps": Regle("jeux", 2, PARTOUT_SAUF_COPIES),  # chaque jeu de steamapps\common
    "epic games": Regle("jeux", 1),
    ".minecraft": Regle("jeux"),
    "riot games": Regle("jeux", 1),
    "xboxgames": Regle("jeux", 1),
    "gog galaxy": Regle("jeux", 1),
    "gog games": Regle("jeux", 1),
    "ubisoft game launcher": Regle("jeux", 2),
    "ea games": Regle("jeux", 1),
    "origin games": Regle("jeux", 1),
    "rockstar games": Regle("jeux", 1),
    "battle.net": Regle("jeux"),
    "roblox": Regle("jeux"),
    "saved games": Regle("jeux", 1),
    "my games": Regle("jeux", 1),
    "games": Regle("jeux", 1, HORS_CLASSEMENT),
    "ankama": Regle("jeux", 1),  # Dofus, Wakfu
    "curseforge": Regle("jeux", 1),  # mods de Minecraft
    "modrinthapp": Regle("jeux", 1),
    "prismlauncher": Regle("jeux", 1),
    "r2modmanplus-local": Regle("jeux", 1),  # mods de jeux Steam
    "thunderstore mod manager": Regle("jeux", 1),
    "hoyoplay": Regle("jeux", 1),  # Genshin Impact, Honkai
    "fivem": Regle("jeux"),
    "itch": Regle("jeux", 1),
    # Outils de programmation : des logiciels installés dans un projet (des copies de fichiers y sont normales).
    ".venv": Regle("applications"),
    "venv": Regle("applications"),
    "node_modules": Regle("applications"),
    "site-packages": Regle("applications"),
    "__pycache__": Regle("applications"),
    ".git": Regle("applications"),
    "windows.old": Regle("sauvegardes"),
    "$windows.~bt": Regle("sauvegardes"),
    "$windows.~ws": Regle("sauvegardes"),
    "mobilesync": Regle("sauvegardes", 2),  # chaque sauvegarde d'iPhone ou d'iPad (iTunes)
    "smartswitch": Regle("sauvegardes"),  # sauvegardes de téléphone Samsung
    "filehistory": Regle("sauvegardes"),
}
# Noms courants des dossiers de cache et de fichiers temporaires.
NOMS_TEMPORAIRES = {"cache", "caches", "cache2", "code cache", "gpucache", "shadercache", "dxcache", "glcache",
                    "d3dscache", "inetcache", "crashdumps", "temp", "tmp"}
REGLES_NOMS |= {nom: Regle("temporaires") for nom in NOMS_TEMPORAIRES}

# Noms qui ne disent pas de quel logiciel il s'agit : « Chrome › Cache » plutôt que « Cache ».
NOMS_VAGUES = NOMS_TEMPORAIRES | {"appdata", "local", "locallow", "roaming", "user data", "default", "localcache",
                                  "programs", "data", "ac"}
SUFFIXE_PAQUET = re.compile(r"_[a-z0-9]{13}$")  # éditeur des applications du Microsoft Store


def regles_emplacements(racine: str) -> dict[str, Regle]:
    """Règles pour des chemins précis de ce disque et de ce PC (clés : os.path.normcase)."""
    systeme = os.environ.get("SystemRoot", r"C:\Windows")
    chemins = {
        systeme: Regle(None),  # Windows : compté dans Système par différence
        tempfile.gettempdir(): Regle("temporaires"),
        str(dossier_local() / "Packages"): Regle("applications", 1),  # applications du Microsoft Store
        str(dossier_local() / "Programs"): Regle("applications", 1),  # logiciels installés pour toi seul
    }
    for nom in ("$Recycle.Bin", "System Volume Information", "Recovery", "$WinREAgent", "Config.Msi"):
        chemins[os.path.join(racine, nom)] = Regle(None)  # Corbeille mesurée à part ; le reste est à Windows
    # Dossiers « .nom » du profil : données d'outils et de logiciels (.vscode, .ollama…), ou cache (.cache).
    try:
        for dossier in Path.home().iterdir():
            if dossier.name.startswith(".") and dossier.is_dir():
                chemins[str(dossier)] = Regle("temporaires" if dossier.name == ".cache" else "applications")
    except OSError:
        pass
    return {os.path.normcase(chemin): regle for chemin, regle in chemins.items()}


def dossiers_windows_temporaires() -> list[str]:
    """Fichiers temporaires rangés dans le dossier Windows, qui lui n'est pas parcouru."""
    systeme = os.environ.get("SystemRoot", r"C:\Windows")
    return [os.path.join(systeme, "Temp"), os.path.join(systeme, "SoftwareDistribution", "Download")]


def nom_element(chemin: str) -> str:
    """Nom parlant d'un dossier ou d'un fichier montré dans la liste."""
    if os.path.normcase(chemin) == os.path.normcase(tempfile.gettempdir()):
        return "Fichiers temporaires de Windows"
    parties = Path(chemin).parts
    nom = SUFFIXE_PAQUET.sub("", parties[-1])
    if Path(chemin).parent == Path.home() and nom.lower() in DOSSIERS_A_TRIER:
        return DOSSIERS_A_TRIER[nom.lower()]  # « Téléchargements » comme dans l'Explorateur, pas « Downloads »
    if [p.lower() for p in parties[-3:-1]] == ["mobilesync", "backup"]:
        return "Sauvegarde d'iPhone ou d'iPad"
    if nom.lower() in NOMS_VAGUES:
        parent = next((p for p in reversed(parties[:-1]) if p.lower() not in NOMS_VAGUES), None)
        if parent:
            return f"{SUFFIXE_PAQUET.sub('', parent)} › {nom}"
    return nom


@cache
def _taille_compressee():
    fonction = ctypes.WinDLL("kernel32", use_last_error=True).GetCompressedFileSizeW
    fonction.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    fonction.restype = wintypes.DWORD
    return fonction


def taille_sur_disque(chemin: str, infos: os.stat_result) -> int:
    """Place réellement prise sur le disque par un fichier."""
    attributs = infos.st_file_attributes
    if attributs & SUR_INTERNET:
        return 0  # fichier OneDrive « disponible en ligne » : il n'est pas sur le PC
    if attributs & REDUIT:
        haut = wintypes.DWORD()
        bas = _taille_compressee()(chemin, ctypes.byref(haut))
        if bas != 0xFFFFFFFF or not ctypes.get_last_error():  # 0xFFFFFFFF peut aussi être une vraie taille
            return haut.value << 32 | bas
    return infos.st_size


class _Comptage:
    """Ce que le parcours additionne, catégorie par catégorie."""

    def __init__(self) -> None:
        self.tailles = {cle: 0 for cle in NOMS}
        self.elements: dict[tuple[str, str], int] = {}  # (catégorie, dossier montré) : octets
        self.dossiers: dict[tuple[str, str], int] = {}  # (catégorie, dossier du fichier) : octets
        self.fichiers: dict[str, list[tuple[int, str]]] = {cle: [] for cle in NOMS}  # plus gros, en tas
        self.speciaux: list[dict] = []  # fichiers de Windows à la racine
        self.octets = self.nombre = self.illisibles = 0
        # Fichiers personnels (ceux classés par extension), pour la recherche de doublons :
        # {dossier: [(nom, taille du contenu)]}, {sous-dossier: dossier parent}, et les dossiers dont une
        # partie n'est pas personnelle ou pas lisible (on ne peut pas les comparer en entier).
        self.perso_fichiers: dict[str, list[tuple[str, int]]] = {}
        self.perso_parents: dict[str, str] = {}
        self.perso_incomplets: set[str] = set()

    def personnels(self) -> dict:
        return {"fichiers": self.perso_fichiers, "parents": self.perso_parents, "incomplets": self.perso_incomplets}

    def ajouter(self, categorie: str, taille: int) -> None:
        self.tailles[categorie] += taille
        self.octets += taille
        self.nombre += 1

    def ajouter_fichier(self, categorie: str, chemin: str, dossier: str, taille: int) -> None:
        """Fichier classé par son extension : il compte pour lui-même et pour son dossier."""
        self.ajouter(categorie, taille)
        cle = (categorie, dossier)
        self.dossiers[cle] = self.dossiers.get(cle, 0) + taille
        tas = self.fichiers[categorie]
        if len(tas) < NB_ELEMENTS:
            heapq.heappush(tas, (taille, chemin))
        elif taille > tas[0][0]:
            heapq.heapreplace(tas, (taille, chemin))


def _enfant(chemin: str, nom: str, categorie: str | None, element: str | None, reste: int,
            regles: dict[str, Regle]) -> tuple[str, str | None, str | None, int] | None:
    """Contexte d'un sous-dossier : (chemin, catégorie, dossier montré, niveaux restants), None s'il est ignoré."""
    regle = regles.get(os.path.normcase(chemin))
    if regle is None:
        regle = REGLES_NOMS.get(nom.lower())
        if regle is not None and categorie not in regle.dans:
            regle = None
    if regle is not None:
        if regle.categorie is None:
            return None
        return chemin, regle.categorie, chemin, regle.profondeur
    if reste:
        reste -= 1
        if not reste:
            element = chemin
    return chemin, categorie, element, reste


def parcourir(racine: str, comptage: _Comptage, regles: dict[str, Regle],
              nouvelles: Callable[[], None], arret: Callable[[], bool], categorie: str | None = None) -> bool:
    """Parcourt le disque depuis `racine` (rangé dans `categorie`, None : à classer) ; faux si l'arrêt a été
    demandé."""
    pile = [(racine, categorie, racine if categorie else None, 0)]
    pile += [(dossier, "temporaires", dossier, 0) for dossier in dossiers_windows_temporaires()
             if os.path.normcase(dossier).startswith(os.path.normcase(racine))]
    while pile:
        if arret():
            return False
        dossier, categorie, element, reste = pile.pop()
        try:
            with os.scandir(dossier) as entrees:
                entrees = list(entrees)
        except OSError:  # dossier protégé : il reste dans Système
            comptage.illisibles += 1
            if categorie is None:
                comptage.perso_incomplets.add(dossier)
            continue
        for entree in entrees:
            try:
                # Jonctions et liens ignorés : ils pointent ailleurs (voire sur eux-mêmes).
                if entree.is_symlink() or entree.is_junction():
                    raise OSError("lien")
                if entree.is_dir(follow_symlinks=False):
                    enfant = _enfant(entree.path, entree.name, categorie, element, reste, regles)
                    if enfant:
                        pile.append(enfant)
                    if categorie is None and (not enfant or enfant[1] is not None):
                        comptage.perso_incomplets.add(dossier)  # contient un dossier de logiciel, de jeu…
                    elif categorie is None:
                        comptage.perso_parents[entree.path] = dossier
                    continue
                # Sous Windows, ces informations viennent de la lecture du dossier : pas d'accès au fichier.
                infos = entree.stat(follow_symlinks=False)
                taille = taille_sur_disque(entree.path, infos)
            except OSError:
                if categorie is None:
                    comptage.perso_incomplets.add(dossier)
                continue
            if categorie is not None:
                comptage.ajouter(categorie, taille)
                cle = (categorie, element or dossier)
                comptage.elements[cle] = comptage.elements.get(cle, 0) + taille
            elif dossier == racine and entree.name.lower() in FICHIERS_SYSTEME:
                comptage.speciaux.append({"nom": FICHIERS_SYSTEME[entree.name.lower()], "chemin": None,
                                          "taille": taille, "dossier": False})
            elif infos.st_file_attributes & FICHIER_SYSTEME:
                continue  # pas un fichier personnel : il reste dans Système (compté par différence)
            else:
                extension = os.path.splitext(entree.name)[1].lower()
                comptage.ajouter_fichier(CATEGORIE_EXTENSION.get(extension, "autres"), entree.path, dossier, taille)
                if infos.st_file_attributes & SUR_INTERNET:
                    comptage.perso_incomplets.add(dossier)  # le lire le téléchargerait : on ne le compare pas
                else:
                    comptage.perso_fichiers.setdefault(dossier, []).append((entree.name, infos.st_size))
        nouvelles()
    return True


def _elements(comptage: _Comptage, cle: str) -> list[dict]:
    """Ce qui prend le plus de place dans une catégorie, du plus gros au plus petit."""
    dossiers = [{"nom": nom_element(chemin), "chemin": chemin, "taille": taille, "dossier": True}
                for (categorie, chemin), taille in comptage.elements.items() if categorie == cle and taille]
    fichiers = [{"nom": os.path.basename(chemin), "chemin": chemin, "taille": taille, "dossier": False}
                for taille, chemin in comptage.fichiers[cle] if taille]
    return sorted(dossiers + fichiers, key=lambda e: e["taille"], reverse=True)[:NB_ELEMENTS]


def _surtout_dans(comptage: _Comptage, cle: str) -> list[dict]:
    """Dossiers qui contiennent le plus de fichiers d'une catégorie classée par extension."""
    if cle not in PAR_EXTENSION:
        return []
    dossiers = sorted(((taille, chemin) for (categorie, chemin), taille in comptage.dossiers.items()
                       if categorie == cle and taille), reverse=True)[:NB_DOSSIERS]
    return [{"nom": nom_element(chemin), "chemin": chemin, "taille": taille} for taille, chemin in dossiers]


def _systeme(utilise: int, hors_systeme: int, speciaux: list[dict]) -> tuple[int, list[dict]]:
    """Système : ce que Windows dit utilisé, moins tout ce qui a été compté ailleurs ; et ses éléments.

    Jamais moins que les fichiers de Windows mesurés (les copies de Windows.old peuvent être comptées en double).
    """
    mesures = sum(e["taille"] for e in speciaux)
    taille = max(mesures, utilise - hors_systeme)
    elements = [{"nom": RESTE_WINDOWS, "chemin": None, "taille": taille - mesures, "dossier": True}] + speciaux
    return taille, sorted((e for e in elements if e["taille"]), key=lambda e: e["taille"], reverse=True)


def disque_systeme() -> str:
    return os.environ.get("SystemDrive", "C:") + os.sep


def scan(racine: str | None = None, progression: Callable[[int, int], None] = lambda *_: None,
         arret: Callable[[], bool] = lambda: False) -> dict | None:
    """Point d'entrée du module (hors score) : ce qui occupe le disque `racine` (ex. « D:\\ »).

    `progression(octets comptés, fichiers comptés)` est appelée régulièrement pendant le parcours.
    Renvoie None si `arret()` devient vrai avant la fin.
    """
    debut = time.perf_counter()
    racine = racine or disque_systeme()
    usage = psutil.disk_usage(racine)
    comptage = _Comptage()
    try:  # la Corbeille du disque est mesurée par Windows : son dossier n'est pas parcouru
        comptage.tailles["corbeille"] = corbeille(racine)
        comptage.octets += comptage.tailles["corbeille"]
    except OSError:
        pass
    derniere = [0.0]

    def nouvelles() -> None:
        if time.perf_counter() - derniere[0] >= INTERVALLE_PROGRESSION:
            derniere[0] = time.perf_counter()
            progression(comptage.octets, comptage.nombre)

    if not parcourir(racine, comptage, regles_emplacements(racine), nouvelles, arret):
        return None

    hors_systeme = sum(taille for cle, taille in comptage.tailles.items() if cle != "systeme")
    comptage.tailles["systeme"], elements_systeme = _systeme(usage.used, hors_systeme, comptage.speciaux)

    categories = []
    for cle, nom, description in CATEGORIES:
        if cle == "systeme":
            elements = elements_systeme
        elif cle == "corbeille":
            taille = comptage.tailles["corbeille"]
            elements = [{"nom": "Corbeille", "chemin": None, "taille": taille, "dossier": True}] if taille else []
        else:
            elements = _elements(comptage, cle)
        categories.append({"cle": cle, "nom": nom, "description": description, "taille": comptage.tailles[cle],
                           "elements": elements, "surtout_dans": _surtout_dans(comptage, cle),
                           "lien": LIENS.get(cle)})
    classees = sorted(categories, key=lambda c: c["taille"], reverse=True)
    principales = ", ".join(f"{c['nom']} ({taille_lisible(c['taille'])})" for c in classees[:3] if c["taille"])
    constats = [f"Disque {racine.rstrip(os.sep)} : {taille_lisible(usage.used)} utilisés sur "
                f"{taille_lisible(usage.total)} ({taille_lisible(usage.free)} libres)."]
    if principales:
        constats.append(f"Ce qui prend le plus de place : {principales}.")
    return {
        "score": None,  # hors score : page Stockage seulement
        "constats": constats,
        "racine": racine,
        "total": usage.total,
        "utilise": usage.used,
        "libre": usage.free,
        "categories": categories,
        "fichiers": comptage.nombre,
        "illisibles": comptage.illisibles,
        "personnels": comptage.personnels(),  # pour modules/doublons.chercher()
        "duree": time.perf_counter() - debut,
    }


# --- Suppression : seulement sur un clic « Supprimer » de la page, après confirmation ---

CLE_DOSSIERS_WINDOWS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"


def dans(chemin: str, dossier: str) -> bool:
    """Vrai si `chemin` est `dossier` lui-même ou se trouve à l'intérieur."""
    return chemin == dossier or chemin.startswith(dossier.rstrip(os.sep) + os.sep)


# Dossiers de Windows et de Microsoft rangés parmi les logiciels (Program Files, ProgramData, AppData…) :
# les supprimer casse Windows. Aussi l'installateur des logiciels (Package Cache) et les anciens Windows.
NOMS_WINDOWS = ("microsoft", "windows", "common files", "internet explorer", "package cache", "packages")
ANCIENS_WINDOWS = {"windows.old", "$windows.~bt", "$windows.~ws"}  # Paramètres > Stockage les supprime


def emplacements_logiciels() -> list[str]:
    """Où Windows range les logiciels et leurs données. Clés : os.path.normcase."""
    local = dossier_local()
    dossiers = [str(local), str(local / "Packages"), str(local / "Programs"), str(local.parent / "LocalLow")]
    dossiers += [os.environ[nom] for nom in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData",
                                             "APPDATA") if os.environ.get(nom)]
    return [os.path.normcase(os.path.abspath(dossier)) for dossier in dossiers]


def dossiers_proteges() -> list[str]:
    """Dossiers à ne jamais supprimer, ni rien qui les contienne : Windows, les emplacements des logiciels,
    les fichiers temporaires, le profil et ses dossiers (Bureau, Documents, Téléchargements…), OneDrive.
    Clés : os.path.normcase."""
    dossiers = [str(Path.home())] + [str(Path.home() / nom) for nom in DOSSIERS_A_TRIER]
    dossiers += [tempfile.gettempdir(), os.environ.get("SystemRoot", r"C:\Windows")]
    dossiers += [os.environ[nom] for nom in ("PUBLIC", "OneDrive", "OneDriveConsumer", "OneDriveCommercial")
                 if os.environ.get(nom)]
    try:  # là où Windows les range vraiment (Bureau déplacé dans OneDrive, Documents sur D:…)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_DOSSIERS_WINDOWS) as cle:
            valeurs = [winreg.EnumValue(cle, i) for i in range(winreg.QueryInfoKey(cle)[1])]
        dossiers += [os.path.expandvars(valeur) for _, valeur, _ in valeurs if isinstance(valeur, str) and valeur]
    except OSError:
        pass
    return [os.path.normcase(os.path.abspath(dossier)) for dossier in dossiers] + emplacements_logiciels()


def supprimable(chemin: str | None) -> bool:
    """Vrai si « Supprimer » est proposé pour un élément montré par l'analyse.

    Tout, sauf ce qui casserait Windows ou le profil : un disque entier, ce qui est dans le dossier Windows,
    les anciens Windows (Windows.old), les dossiers de Windows et de Microsoft rangés parmi les logiciels,
    les emplacements des logiciels eux-mêmes, le dossier des fichiers temporaires, le profil, Bureau,
    Documents, Téléchargements… ni un dossier qui en contient un.
    """
    if not chemin:
        return False
    cible = os.path.normcase(os.path.abspath(chemin))
    parent, nom = os.path.split(cible)
    if parent == cible or nom in ANCIENS_WINDOWS:
        return False
    if dans(cible, os.path.normcase(os.environ.get("SystemRoot", r"C:\Windows"))):
        return False
    racine = os.path.splitdrive(cible)[0] + os.sep
    if nom.startswith(NOMS_WINDOWS) and parent in [racine, *emplacements_logiciels()]:
        return False
    return not any(dans(protege, cible) for protege in dossiers_proteges())


def contenu(chemin: str, categorie: str | None = None) -> tuple[dict[str, int], int]:
    """Place prise par catégorie et nombre de fichiers d'un fichier ou d'un dossier, classés comme pendant
    l'analyse. `categorie` : celle où l'analyse l'a rangé (None, ou une catégorie classée par extension :
    chaque fichier est classé selon son emplacement puis son extension).

    Mesuré avant la suppression (pour la confirmation), puis après (ce qui n'a pas pu partir).
    OSError s'il n'existe plus.
    """
    contexte = None if categorie in PAR_EXTENSION else categorie
    comptage = _Comptage()
    infos = os.stat(chemin, follow_symlinks=False)
    if stat.S_ISDIR(infos.st_mode):
        disque = os.path.splitdrive(chemin)[0] + os.sep
        parcourir(chemin, comptage, regles_emplacements(disque), lambda: None, lambda: False, contexte)
    elif contexte:
        comptage.ajouter(contexte, taille_sur_disque(chemin, infos))
    elif not infos.st_file_attributes & FICHIER_SYSTEME:  # un fichier de Windows reste dans Système
        extension = os.path.splitext(chemin)[1].lower()
        comptage.ajouter(CATEGORIE_EXTENSION.get(extension, "autres"), taille_sur_disque(chemin, infos))
    return {cle: taille for cle, taille in comptage.tailles.items() if taille}, comptage.nombre


def retirer(resultat: dict, chemin: str, dossier: bool, enleve: dict[str, int]) -> None:
    """Met l'analyse à jour après la suppression de `chemin`.

    `enleve` : place qui a vraiment quitté chaque catégorie (contenu() avant, moins après). L'espace utilisé
    est remesuré, Système est recalculé comme pendant l'analyse, et ce qui a disparu n'est plus montré.
    """
    usage = psutil.disk_usage(resultat["racine"])
    resultat["utilise"], resultat["libre"] = usage.used, usage.free
    categories = {c["cle"]: c for c in resultat["categories"]}
    for cle, octets in enleve.items():
        categories[cle]["taille"] = max(0, categories[cle]["taille"] - octets)

    for categorie in resultat["categories"]:
        categorie["elements"] = [e for e in categorie["elements"] if not (
            e["chemin"] and dans(e["chemin"], chemin) and not os.path.lexists(e["chemin"]))]
        lieux = []
        for lieu in categorie["surtout_dans"]:
            if dans(lieu["chemin"], chemin) and not os.path.lexists(lieu["chemin"]):
                continue
            if not dossier and lieu["chemin"] == os.path.dirname(chemin):  # le fichier était rangé là
                lieu["taille"] -= enleve.get(categorie["cle"], 0)
            if lieu["taille"] > 0:
                lieux.append(lieu)
        categorie["surtout_dans"] = sorted(lieux, key=lambda lieu: lieu["taille"], reverse=True)

    systeme = categories["systeme"]
    speciaux = [e for e in systeme["elements"] if e["nom"] != RESTE_WINDOWS]
    hors_systeme = sum(c["taille"] for c in resultat["categories"] if c["cle"] != "systeme")
    systeme["taille"], systeme["elements"] = _systeme(usage.used, hors_systeme, speciaux)
