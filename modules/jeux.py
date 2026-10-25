"""Module jeux et affichage (hors score) : fréquence des écrans, pilote de la carte graphique et Mode jeu.

Lecture seule : on demande à Windows les réglages des écrans et on lit le registre, on ne change rien.
"""

import ctypes
import uuid
import winreg
from ctypes import wintypes
from datetime import date

import psutil

# Vraies cartes graphiques : les écrans virtuels (Microsoft, logiciels de partage d'écran…) n'ont rien à régler.
FABRICANTS = {"NVIDIA": "NVIDIA", "Advanced Micro Devices, Inc.": "AMD", "AMD": "AMD",
              "ATI Technologies Inc.": "AMD", "Intel Corporation": "Intel"}
CLASSE_AFFICHAGE = "4d36e968-e325-11ce-bfc1-08002be10318"  # GUID_DEVCLASS_DISPLAY
CLE_CLASSES = r"SYSTEM\CurrentControlSet\Control\Class"
CLE_MODE_JEU = r"Software\Microsoft\GameBar"
ATTACHE_AU_BUREAU, PRINCIPAL = 0x1, 0x4  # DISPLAY_DEVICE_ATTACHED_TO_DESKTOP, DISPLAY_DEVICE_PRIMARY_DEVICE
MODE_ACTUEL = -1  # ENUM_CURRENT_SETTINGS
ENTRELACE = 0x2  # DM_INTERLACED : image moins nette, pas un vrai réglage à conseiller
DIGCF_PRESENT = 0x2
SPDRP_DRIVER = 9  # nom de la clé du pilote, sous CLE_CLASSES


class _Peripherique(ctypes.Structure):  # DISPLAY_DEVICEW
    _fields_ = [("taille", wintypes.DWORD), ("nom", wintypes.WCHAR * 32), ("description", wintypes.WCHAR * 128),
                ("etat", wintypes.DWORD), ("identifiant", wintypes.WCHAR * 128), ("cle", wintypes.WCHAR * 128)]


class _Mode(ctypes.Structure):  # DEVMODEW (partie écran)
    _fields_ = [("nom", wintypes.WCHAR * 32), ("version", wintypes.WORD), ("version_pilote", wintypes.WORD),
                ("taille", wintypes.WORD), ("extra", wintypes.WORD), ("champs", wintypes.DWORD),
                ("position", ctypes.c_byte * 16), ("couleur", ctypes.c_short * 5), ("formulaire", wintypes.WCHAR * 32),
                ("pixels_logiques", wintypes.WORD), ("bits", wintypes.DWORD), ("largeur", wintypes.DWORD),
                ("hauteur", wintypes.DWORD), ("drapeaux", wintypes.DWORD), ("frequence", wintypes.DWORD),
                ("reste", wintypes.DWORD * 8)]


class _InfoAppareil(ctypes.Structure):  # SP_DEVINFO_DATA
    _fields_ = [("taille", wintypes.DWORD), ("classe", ctypes.c_ubyte * 16), ("instance", wintypes.DWORD),
                ("reserve", ctypes.c_void_p)]


def _modes(user32: ctypes.WinDLL, peripherique: str) -> list[_Mode]:
    """Tous les modes (résolution, fréquence…) qu'accepte l'écran branché sur `peripherique`."""
    modes, numero = [], 0
    while True:
        mode = _Mode(taille=ctypes.sizeof(_Mode))
        if not user32.EnumDisplaySettingsW(peripherique, numero, ctypes.byref(mode)):
            return modes
        modes.append(mode)
        numero += 1


def frequence_maximale(modes: list[tuple[int, int, int, int]], largeur: int, hauteur: int) -> int:
    """La plus haute fréquence (Hz) acceptée à cette résolution ; modes : (largeur, hauteur, fréquence, drapeaux).

    Un écran tourné d'un quart de tour peut lister ses modes dans l'autre sens : les deux comptent.
    """
    return max((frequence for l, h, frequence, drapeaux in modes
                if (largeur, hauteur) in ((l, h), (h, l)) and not drapeaux & ENTRELACE), default=0)


def ecrans() -> list[dict]:
    """Chaque écran allumé, le principal d'abord : résolution, fréquence utilisée et fréquence maximale à cette
    résolution (en Hz)."""
    user32 = ctypes.WinDLL("user32")
    trouves, numero = [], 0
    while True:
        peripherique = _Peripherique(taille=ctypes.sizeof(_Peripherique))
        if not user32.EnumDisplayDevicesW(None, numero, ctypes.byref(peripherique), 0):
            break
        numero += 1
        actuel = _Mode(taille=ctypes.sizeof(_Mode))
        if (not peripherique.etat & ATTACHE_AU_BUREAU
                or not user32.EnumDisplaySettingsW(peripherique.nom, MODE_ACTUEL, ctypes.byref(actuel))
                or actuel.frequence <= 1):  # 0 ou 1 : « fréquence par défaut du matériel », inconnue
            continue
        modes = [(m.largeur, m.hauteur, m.frequence, m.drapeaux) for m in _modes(user32, peripherique.nom)]
        trouves.append({"principal": bool(peripherique.etat & PRINCIPAL), "largeur": actuel.largeur,
                        "hauteur": actuel.hauteur, "frequence": actuel.frequence,
                        "maximum": max(actuel.frequence, frequence_maximale(modes, actuel.largeur, actuel.hauteur))})
    return sorted(trouves, key=lambda ecran: not ecran["principal"])


def date_pilote(texte: object) -> date | None:
    """Date d'un pilote telle que Windows la note (« 9-17-2026 », mois en premier), ou None."""
    try:
        mois, jour, annee = (int(nombre) for nombre in str(texte).split("-"))
        return date(annee, mois, jour)
    except ValueError:
        return None


def _cles_pilotes() -> list[str]:
    """Clé du pilote (sous CLE_CLASSES) de chaque carte graphique présente dans le PC."""
    setupapi = ctypes.WinDLL("setupapi")
    setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    setupapi.SetupDiEnumDeviceInfo.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
    setupapi.SetupDiGetDeviceRegistryPropertyW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                                           ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                                           ctypes.c_void_p]
    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    classe = (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(CLASSE_AFFICHAGE).bytes_le)
    liste = setupapi.SetupDiGetClassDevsW(ctypes.byref(classe), None, None, DIGCF_PRESENT)
    if liste in (None, ctypes.c_void_p(-1).value):
        return []
    cles = []
    try:
        numero = 0
        while True:
            appareil = _InfoAppareil(taille=ctypes.sizeof(_InfoAppareil))
            if not setupapi.SetupDiEnumDeviceInfo(liste, numero, ctypes.byref(appareil)):
                break
            numero += 1
            tampon = ctypes.create_unicode_buffer(256)
            if setupapi.SetupDiGetDeviceRegistryPropertyW(liste, ctypes.byref(appareil), SPDRP_DRIVER, None,
                                                          tampon, ctypes.sizeof(tampon), None):
                cles.append(tampon.value)
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(liste)
    return cles


def _valeur(cle, nom: str) -> object:
    try:
        return winreg.QueryValueEx(cle, nom)[0]
    except OSError:
        return None


def cartes_graphiques(aujourd_hui: date | None = None) -> list[dict]:
    """Cartes graphiques présentes d'un vrai fabricant : nom, fabricant, date et âge du pilote (jours), mémoire."""
    aujourd_hui = aujourd_hui or date.today()
    cartes = []
    for cle_pilote in _cles_pilotes():
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"{CLE_CLASSES}\{cle_pilote}") as cle:
                nom, fournisseur = _valeur(cle, "DriverDesc"), _valeur(cle, "ProviderName")
                pilote = date_pilote(_valeur(cle, "DriverDate"))
                memoire = (_valeur(cle, "HardwareInformation.qwMemorySize")
                           or _valeur(cle, "HardwareInformation.MemorySize"))
        except OSError:  # clé illisible : carte ignorée
            continue
        if fournisseur not in FABRICANTS or not nom:
            continue
        cartes.append({"nom": nom, "fabricant": FABRICANTS[fournisseur], "date": pilote,
                       "age": (aujourd_hui - pilote).days if pilote else None,
                       "memoire": memoire if isinstance(memoire, int) else 0})
    return cartes


def carte_des_jeux(cartes: list[dict]) -> dict | None:
    """Celle qui fait tourner les jeux : la plus de mémoire dédiée (sur un PC portable à deux cartes, la carte
    graphique séparée plutôt que celle intégrée au processeur)."""
    return max(cartes, key=lambda carte: carte["memoire"], default=None)


def mode_jeu() -> bool:
    """Vrai si le Mode jeu de Windows est activé (il l'est par défaut : seul un 0 noté par Windows le coupe)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_MODE_JEU) as cle:
            return _valeur(cle, "AutoGameModeEnabled") != 0
    except OSError:  # clé absente : réglage jamais changé
        return True


def constats(liste_ecrans: list[dict], cartes: list[dict], carte: dict | None, actif: bool) -> list[str]:
    lignes = []
    for numero, ecran in enumerate(liste_ecrans, start=1):
        nom = "Écran" if len(liste_ecrans) == 1 else f"Écran {numero}" + (" (principal)" if ecran["principal"] else "")
        reglage = f"{nom} : {ecran['frequence']} Hz en {ecran['largeur']} × {ecran['hauteur']}"
        if ecran["maximum"] - ecran["frequence"] > 2:  # 59 et 60 Hz : la même fréquence, arrondie différemment
            lignes.append(f"{reglage}, alors qu'il peut aller jusqu'à {ecran['maximum']} Hz.")
        else:
            lignes.append(f"{reglage}, le maximum de cet écran.")
    if not liste_ecrans:
        lignes.append("Fréquence de l'écran non lisible sur ce PC.")
    for autre in sorted(cartes, key=lambda c: c is not carte):  # celle des jeux d'abord
        quoi = "Carte graphique" if len(cartes) == 1 else ("Carte graphique pour les jeux" if autre is carte
                                                           else "Autre carte graphique")
        quand = f", pilote du {autre['date']:%d/%m/%Y}" if autre["date"] else ""
        lignes.append(f"{quoi} : {autre['nom']}{quand}.")
    if not cartes:
        lignes.append("Carte graphique non reconnue.")
    lignes.append(f"Mode jeu de Windows : {'activé' if actif else 'désactivé'}.")
    return lignes


def scan() -> dict:
    """Point d'entrée du module (hors score) : renvoie les réglages lus et les constats."""
    liste_ecrans, cartes, actif = ecrans(), cartes_graphiques(), mode_jeu()
    carte = carte_des_jeux(cartes)
    batterie = psutil.sensors_battery()
    return {
        "score": None,  # hors score : voir modules/score.conseils_jeux()
        "constats": constats(liste_ecrans, cartes, carte, actif),
        "ecrans": liste_ecrans,
        "cartes": cartes,
        "carte_jeux": carte,
        "mode_jeu": actif,
        "sur_batterie": batterie is not None and batterie.power_plugged is False,
    }
