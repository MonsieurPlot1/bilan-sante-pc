"""Module pilotes (hors score) : les pilotes que Windows Update propose, la dernière version du pilote NVIDIA, et les
pilotes des composants du PC qui ont plus de deux ans.

Lecture seule : on lit le registre et ce que Windows Update a trouvé lors de sa dernière recherche (sur le PC, sans
réseau), et on demande à NVIDIA la dernière version de son pilote : seuls les numéros de produit de la carte graphique
et la version de Windows partent. L'installation, seulement sur clic, est dans modules/installation_pilotes.py.
"""

import base64
import ctypes
import http.client
import json
import logging
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import uuid
import winreg
import xml.etree.ElementTree as ElementTree
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from datetime import date

import config

journal = logging.getLogger(__name__)

CLE_CLASSES = r"SYSTEM\CurrentControlSet\Control\Class"
CLE_POLITIQUE = r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate"
CLE_BIOS = r"HARDWARE\DESCRIPTION\System\BIOS"
DIGCF_PRESENT, DIGCF_ALLCLASSES = 0x2, 0x4
SPDRP_DRIVER = 9  # nom de la clé du pilote, sous CLE_CLASSES

# Classes d'appareils qui comptent (nom affiché) : les composants logiciels, effets audio et micrologiciels (BIOS) ne
# se mettent pas à jour à part.
CATEGORIES = {"Display": "Carte graphique", "System": "Carte mère et processeur",
              "SecurityDevices": "Carte mère et processeur", "HDC": "Carte mère et processeur",
              "SCSIAdapter": "Carte mère et processeur", "USB": "Carte mère et processeur", "MEDIA": "Son",
              "Net": "Réseau", "Bluetooth": "Bluetooth", "HIDClass": "Pavé tactile et clavier", "Camera": "Caméra",
              "Image": "Caméra", "Biometric": "Lecteur d'empreinte", "Sensor": "Capteurs"}
# Fabricants de composants : leurs pilotes viennent avec le PC. Ceux des accessoires (clavier, casque…) viennent avec
# le logiciel de l'accessoire, et ne sont pas comptés.
COMPOSANTS = ("advanced micro devices", "amd", "intel", "nvidia", "realtek", "mediatek", "qualcomm", "broadcom",
              "synaptics", "elan", "rivet networks", "killer", "conexant", "cirrus logic", "marvell")

# Application du fabricant du PC qui propose ses pilotes (nom dans le menu Démarrer), par ordre de préférence.
OUTILS_FABRICANTS = ["MyASUS", "Lenovo Vantage", "Lenovo Commercial Vantage", "HP Support Assistant",
                     "Dell Command | Update", "SupportAssist", "MSI Center", "Acer Care Center", "Samsung Update"]

# NVIDIA : liste des produits (numéros de série et de produit), puis dernière version publiée pour l'un d'eux.
NVIDIA_PRODUITS = "https://www.nvidia.com/Download/API/lookupValueSearch.aspx?TypeID=3"
NVIDIA_RECHERCHE = ("https://gfwsl.geforce.com/services_toolkit/services/com/nvidia/services/AjaxDriverService.php"
                    "?func=DriverManualLookup&psid={psid}&pfid={pfid}&osID={os}&languageCode=1036&beta=0&isWHQL=1"
                    "&dltype=-1&dch=1&upCRD=0&qnf=0&sort1=0&numberOfResults=1")
NVIDIA_WINDOWS_11, NVIDIA_WINDOWS_10 = 135, 57  # osID : Windows 64 bits
ORIGINE_NVIDIA = re.compile(r"^https://[a-z]+\.download\.nvidia\.com/Windows/[\w.\-/]+\.exe$")
ENTETES = {"User-Agent": f"BilanSantePC/{config.VERSION}"}
DELAI = 10  # secondes sans réponse avant d'abandonner
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
        "décembre"]

# Une seule commande PowerShell : les pilotes trouvés par la dernière recherche de Windows Update (sans réseau), et
# les applications du menu Démarrer (pour trouver celle du fabricant du PC).
SCRIPT_RECHERCHE = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$resultat = @{}
try {
  $chercheur = (New-Object -ComObject Microsoft.Update.Session).CreateUpdateSearcher()
  $chercheur.Online = $false
  $resultat.mises_a_jour = @($chercheur.Search("IsInstalled=0 and Type='Driver'").Updates | ForEach-Object {
    @{ id = $_.Identity.UpdateID; titre = $_.Title; modele = $_.DriverModel; fabricant = $_.DriverManufacturer;
       date = $_.DriverVerDate.ToString('yyyy-MM-dd'); taille = [long]$_.MaxDownloadSize } })
} catch { $resultat.erreur = $_.Exception.Message }
try { $resultat.applis = @(Get-StartApps | ForEach-Object { @{ nom = $_.Name; id = $_.AppID } }) } catch {}
ConvertTo-Json $resultat -Depth 4 -Compress
"""


class _InfoAppareil(ctypes.Structure):  # SP_DEVINFO_DATA
    _fields_ = [("taille", wintypes.DWORD), ("classe", ctypes.c_ubyte * 16), ("instance", wintypes.DWORD),
                ("reserve", ctypes.c_void_p)]


# --- Pilotes installés ---

def cles_pilotes(classe: str | None = None) -> list[str]:
    """Clé du pilote (sous CLE_CLASSES) de chaque appareil présent, de la classe `classe` (GUID) ou de toutes."""
    setupapi = ctypes.WinDLL("setupapi")
    setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    setupapi.SetupDiEnumDeviceInfo.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
    setupapi.SetupDiGetDeviceRegistryPropertyW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                                           ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                                           ctypes.c_void_p]
    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    if classe:
        guid = (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(classe).bytes_le)
        liste = setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, DIGCF_PRESENT)
    else:
        liste = setupapi.SetupDiGetClassDevsW(None, None, None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
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


def valeur(cle, nom: str) -> object:
    try:
        return winreg.QueryValueEx(cle, nom)[0]
    except OSError:
        return None


def date_pilote(texte: object) -> date | None:
    """Date d'un pilote telle que Windows la note (« 9-17-2026 », mois en premier), ou None."""
    try:
        mois, jour, annee = (int(nombre) for nombre in str(texte).split("-"))
        return date(annee, mois, jour)
    except ValueError:
        return None


def pilotes_installes(aujourd_hui: date | None = None) -> list[dict]:
    """Pilote de chaque appareil présent d'une classe qui compte (CATEGORIES), sans doublon : nom, catégorie,
    fournisseur, version, date et âge (jours)."""
    aujourd_hui = aujourd_hui or date.today()
    pilotes, vus = [], set()
    for cle_pilote in cles_pilotes():
        try:
            guid_classe = cle_pilote.rsplit("\\", 1)[0]  # « {4d36e968-…}\0000 » : la clé de la classe, puis le numéro
            with (winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"{CLE_CLASSES}\{cle_pilote}") as cle,
                  winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"{CLE_CLASSES}\{guid_classe}") as classe):
                categorie = CATEGORIES.get(valeur(classe, "Class"))
                nom, fournisseur = valeur(cle, "DriverDesc"), valeur(cle, "ProviderName")
                version, quand = valeur(cle, "DriverVersion"), date_pilote(valeur(cle, "DriverDate"))
        except OSError:  # clé illisible : appareil ignoré
            continue
        if not categorie or not nom or not isinstance(fournisseur, str) or (nom, version) in vus:
            continue
        vus.add((nom, version))
        pilotes.append({"nom": nom, "categorie": categorie, "fournisseur": fournisseur, "version": str(version or ""),
                        "date": quand, "age": (aujourd_hui - quand).days if quand else None})
    return pilotes


def fabricant_du_pc() -> str:
    """Fabricant du PC, tel que son BIOS le donne (« ASUSTeK COMPUTER INC. »), ou une chaîne vide."""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CLE_BIOS) as cle:
            return str(valeur(cle, "SystemManufacturer") or "").strip()
    except OSError:
        return ""


def du_pc(pilote: dict, fabricant: str) -> bool:
    """Vrai pour un pilote de composant du PC (fabricant de puces, ou fabricant du PC lui-même)."""
    fournisseur = pilote["fournisseur"].lower()
    marque = fabricant.lower().split(" ")[0] if fabricant else ""
    return fournisseur.startswith(COMPOSANTS) or bool(marque) and fournisseur.startswith(marque)


def pilotes_bloques() -> bool:
    """Vrai si Windows est réglé pour ne jamais installer de pilotes par Windows Update (stratégie de groupe)."""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CLE_POLITIQUE) as cle:
            return valeur(cle, "ExcludeWUDriversInQualityUpdate") == 1
    except OSError:
        return False


# --- Windows Update et application du fabricant (PowerShell) ---

def _powershell(script: str, delai: float = 60) -> str:
    """Lance `script` dans PowerShell, sans fenêtre, et renvoie ce qu'il écrit."""
    commande = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-EncodedCommand", base64.b64encode(script.encode("utf-16-le")).decode("ascii")]
    sortie = subprocess.run(commande, capture_output=True, timeout=delai, check=True,
                            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
    return sortie.stdout.decode("utf-8", errors="replace")


def mise_a_jour_lue(element: dict) -> dict:
    return {"id": str(element["id"]), "nom": element.get("modele") or element["titre"], "titre": element["titre"],
            "fabricant": element.get("fabricant") or "", "taille": int(element.get("taille") or 0),
            "date": date.fromisoformat(element["date"]) if element.get("date") else None}


def outil_du_fabricant(applis: list[dict]) -> dict | None:
    """L'application du fabricant du PC qui propose ses pilotes, si elle est installée : nom et cible à ouvrir."""
    par_nom = {appli.get("nom"): appli.get("id") for appli in applis}
    for nom in OUTILS_FABRICANTS:
        if par_nom.get(nom):
            return {"nom": nom, "cible": rf"shell:AppsFolder\{par_nom[nom]}"}
    return None


def interroger_windows() -> dict:
    """Pilotes proposés par Windows Update (None si illisible) et application du fabricant du PC."""
    try:
        lu = json.loads(_powershell(SCRIPT_RECHERCHE))
        applis = lu.get("applis") or []
        if lu.get("erreur"):
            journal.warning("Windows Update illisible : %s", lu["erreur"])
            return {"mises_a_jour": None, "outil": outil_du_fabricant(applis)}
        return {"mises_a_jour": [mise_a_jour_lue(element) for element in lu.get("mises_a_jour") or []],
                "outil": outil_du_fabricant(applis)}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError):
        journal.warning("Recherche des pilotes de Windows Update impossible", exc_info=True)
        return {"mises_a_jour": None, "outil": None}


# --- NVIDIA ---

def version_nvidia(version_windows: str) -> str | None:
    """Numéro de version NVIDIA (« 617.14 ») d'un pilote noté par Windows (« 32.0.16.1714 »)."""
    morceaux = version_windows.split(".")
    if len(morceaux) != 4 or not all(morceau.isdigit() for morceau in morceaux):
        return None
    chiffres = (morceaux[2] + morceaux[3].zfill(4))[-5:]
    return f"{int(chiffres[:3])}.{chiffres[3:]}"


def plus_recente(version: str, autre: str) -> bool:
    """Vrai si la version NVIDIA `version` est plus récente que `autre`."""
    return tuple(int(n) for n in version.split(".")) > tuple(int(n) for n in autre.split("."))


def numeros_produit(xml: bytes, nom: str) -> tuple[str, str] | None:
    """(série, produit) de la carte `nom` dans la liste des produits de NVIDIA, ou None."""
    cherche = nom.lower().removeprefix("nvidia ").strip()
    for produit in ElementTree.fromstring(xml).iter("LookupValue"):
        if (produit.findtext("Name") or "").strip().lower() == cherche:
            return produit.get("ParentID"), produit.findtext("Value")
    return None


def date_nvidia(texte: str) -> date | None:
    """Date de sortie telle que NVIDIA la donne en français (« 2026 octobre 21 »), ou None."""
    try:
        annee, mois, jour = texte.split()
        return date(int(annee), MOIS.index(mois.lower()) + 1, int(jour))
    except ValueError:
        return None


def taille_nvidia(texte: str) -> int:
    """Taille approximative en octets (« 1.04 GB », « 990.85 MB »), 0 si illisible."""
    nombre, _, unite = texte.partition(" ")
    try:
        return round(float(nombre) * {"GB": 1024**3, "MB": 1024**2}[unite.strip().upper()])
    except (ValueError, KeyError):
        return 0


def derniere_nvidia(reponse: bytes) -> dict | None:
    """Dernière version publiée, d'après la réponse de NVIDIA : version, date, adresse et taille du fichier."""
    trouvees = json.loads(reponse).get("IDS") or []
    if not trouvees:
        return None
    infos = trouvees[0]["downloadInfo"]
    url = infos["DownloadURL"]
    if not ORIGINE_NVIDIA.match(url):
        raise ValueError(f"Adresse de téléchargement inattendue : {url}")
    return {"version": infos["Version"], "date": date_nvidia(urllib.parse.unquote(infos.get("ReleaseDateTime", ""))),
            "url": url, "taille": taille_nvidia(infos.get("DownloadURLFileSize", ""))}


def _ouvrir(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=ENTETES), timeout=DELAI) as reponse:
        return reponse.read(8 * 1024**2)  # liste des produits : moins de 100 Ko


def verifier_nvidia(carte: dict) -> dict:
    """La carte NVIDIA, sa version installée et la dernière publiée (« derniere » à None : non vérifiable)."""
    resultat = {"carte": carte["nom"], "installee": version_nvidia(carte["version"]), "derniere": None}
    try:
        numeros = numeros_produit(_ouvrir(NVIDIA_PRODUITS), carte["nom"])
        if numeros is None:
            journal.info("Carte NVIDIA absente de la liste des produits : %s", carte["nom"])
            return resultat
        windows = NVIDIA_WINDOWS_11 if sys.getwindowsversion().build >= 22000 else NVIDIA_WINDOWS_10
        resultat["derniere"] = derniere_nvidia(_ouvrir(NVIDIA_RECHERCHE.format(psid=numeros[0], pfid=numeros[1],
                                                                                os=windows)))
    except (OSError, http.client.HTTPException, ValueError, KeyError, TypeError, ElementTree.ParseError):
        journal.warning("Dernière version NVIDIA introuvable", exc_info=True)
    return resultat


def nvidia_a_installer(nvidia: dict | None) -> bool:
    return bool(nvidia and nvidia["installee"] and nvidia["derniere"]
                and plus_recente(nvidia["derniere"]["version"], nvidia["installee"]))


# --- Constats ---

def constats(nvidia: dict | None, mises_a_jour: list[dict] | None, bloques: bool, anciens: list[dict],
             outil: dict | None, fabricant: str) -> list[str]:
    lignes = []
    if nvidia:
        installee = f"pilote {nvidia['installee']}" if nvidia["installee"] else "pilote installé"
        if nvidia_a_installer(nvidia):
            derniere = nvidia["derniere"]
            sortie = f", sortie le {derniere['date']:%d/%m/%Y}" if derniere["date"] else ""
            lignes.append(f"{nvidia['carte']} : {installee}, la version {derniere['version']} est disponible{sortie}.")
        elif nvidia["derniere"]:
            lignes.append(f"{nvidia['carte']} : {installee}, le plus récent.")
        else:
            lignes.append(f"{nvidia['carte']} : {installee} (dernière version non vérifiable : pas de connexion ?).")
    if mises_a_jour is None:
        lignes.append("Windows Update n'a pas pu être consulté.")
    elif mises_a_jour:
        noms = (", ".join(mise_a_jour["nom"] for mise_a_jour in mises_a_jour[:3])
                + ("…" if len(mises_a_jour) > 3 else ""))
        lignes.append(f"Windows Update propose {len(mises_a_jour)} pilote{'s' if len(mises_a_jour) > 1 else ''} : "
                      f"{noms}.")
    else:
        lignes.append("Windows Update ne propose aucun pilote.")
    if bloques:
        lignes.append("Windows est réglé pour ne jamais installer de pilotes par Windows Update (réglage souvent "
                      "posé par un logiciel d'optimisation ou par une entreprise).")
    if anciens:
        ou = outil["nom"] if outil else "le site du fabricant du PC" + (f" ({fabricant})" if fabricant else "")
        lignes.append(f"{len(anciens)} pilote{'s' if len(anciens) > 1 else ''} du PC "
                      f"{'ont' if len(anciens) > 1 else 'a'} plus de 2 ans : {ou} dit s'il en existe des plus récents.")
    else:
        lignes.append("Les pilotes des composants du PC ont tous moins de 2 ans.")
    return lignes


def scan() -> dict:
    """Point d'entrée du module (hors score) : pilotes à mettre à jour, et ceux à vérifier chez le fabricant."""
    fabricant = fabricant_du_pc()
    pilotes = [pilote for pilote in pilotes_installes() if du_pc(pilote, fabricant)]
    carte = next((pilote for pilote in pilotes if pilote["categorie"] == "Carte graphique"
                  and pilote["fournisseur"].lower().startswith("nvidia")), None)
    # Windows Update (PowerShell, quelques secondes) et NVIDIA (réseau) en même temps.
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="pilotes") as executeur:
        windows = executeur.submit(interroger_windows)
        nvidia = verifier_nvidia(carte) if carte else None
        windows = windows.result()
    anciens = [pilote for pilote in pilotes if pilote["age"] is not None and pilote["age"] > config.PILOTE_ANCIEN_AGE
               and not (carte and pilote is carte)]
    bloques = pilotes_bloques()
    mises_a_jour = windows["mises_a_jour"]
    return {
        "score": None,  # hors score : voir modules/score.conseils_pilotes()
        "constats": constats(nvidia, mises_a_jour, bloques, anciens, windows["outil"], fabricant),
        "pilotes": sorted(pilotes, key=lambda pilote: (pilote["date"] or date.min)),
        "anciens": anciens,
        "nvidia": nvidia,
        "mises_a_jour": mises_a_jour,
        "bloques": bloques,
        "outil": windows["outil"],
        "fabricant": fabricant,
        "a_installer": len(mises_a_jour or []) + nvidia_a_installer(nvidia),
    }
