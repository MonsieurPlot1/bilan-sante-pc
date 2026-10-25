"""Module connexion internet (onglet à part, hors du bilan) : la liaison avec la box et un test de débit réel.

La liaison (Wi-Fi ou câble, signal, vitesse avec la box) se lit auprès de Windows, sans rien envoyer.
Le test est la seule partie de l'application qui utilise le réseau, et seulement sur clic : il mesure le ping,
puis télécharge et envoie des données de test (tirées au hasard) avec les serveurs de Cloudflare
(speed.cloudflare.com). Rien d'autre ne part : ni fichier, ni résultat du bilan, ni information sur le PC.
"""

import ctypes
import http.client
import logging
import os
import socket
import ssl
import statistics
import threading
import time
import uuid
from ctypes import wintypes
from datetime import datetime
from typing import Callable

import psutil

journal = logging.getLogger(__name__)

SERVEUR = "speed.cloudflare.com"
PORT = 443
ENTETES = {"User-Agent": "BilanSantePC"}  # le nom de l'application, rien sur le PC
DELAI = 10  # secondes sans réponse du serveur avant d'abandonner

NB_PINGS = 10
ECART_PINGS = 0.1  # secondes entre deux pings : ils mesurent la connexion au repos, pas une rafale
FLUX = 4  # connexions en même temps : une seule ne suffit pas à remplir une connexion rapide (fibre)
DUREE_MESURE = 8.0  # secondes au plus pour chaque sens
PART_CHAUFFE = 0.3  # premiers 30 % des données non comptés : le débit y monte en puissance
# Octets au plus par sens : sur la fibre, la mesure s'arrête avant DUREE_MESURE (à 1 Gbit/s : 2 s environ).
# Bien moins que le test de Cloudflare lui-même (jusqu'à 1 Go) : le serveur bloque une heure les connexions qui
# enchaînent trop de tests (vu en essai, après 1,5 Go en quelques minutes).
LIMITE = {"descendant": 250 * 10**6, "montant": 100 * 10**6}
TAILLE_REQUETE = {"descendant": 25 * 10**6, "montant": 10 * 10**6}
BLOC = 64 * 1024
SEUIL_TRAFIC = 2.0  # Mbit/s déjà utilisés par d'autres programmes avant le test : le résultat est sous-estimé

LIEN_WIFI = ("Ouvrir les Paramètres", "ms-settings:network-wifi")
LIEN_RESEAU = ("Ouvrir les paramètres réseau", "ms-settings:network-status")

# Types d'interface de Windows (IANA ifType).
TYPES = {6: "cable", 71: "wifi", 243: "mobile", 244: "mobile"}
NOMS_TYPES = {"wifi": "Wi-Fi", "cable": "Câble réseau (Ethernet)", "mobile": "Réseau mobile (4G, 5G)",
              "autre": "Autre (VPN, partage de connexion…)"}
# Norme Wi-Fi selon le type de radio (DOT11_PHY_TYPE) : 4 à 6 = 802.11a, b et g.
NORMES = {4: "ancien Wi-Fi (802.11a)", 5: "ancien Wi-Fi (802.11b)", 6: "ancien Wi-Fi (802.11g)", 7: "Wi-Fi 4",
          8: "Wi-Fi 5", 10: "Wi-Fi 6", 11: "Wi-Fi 7"}
PHY_WIFI_6 = 10

# Ce que la connexion permet : (usage, condition sur les mesures). Débits en Mbit/s, ping et gigue en ms.
USAGES = [
    ("Navigation web et e-mails", lambda m: m["descendant"] >= 2),
    ("Vidéo en HD (YouTube, Netflix…)", lambda m: m["descendant"] >= 5),
    ("Vidéo en 4K", lambda m: m["descendant"] >= 25),
    ("Appels vidéo (Teams, Zoom, Discord…)",
     lambda m: m["descendant"] >= 3 and m["montant"] >= 3 and m["ping"] <= 150),
    ("Jeux en ligne", lambda m: m["descendant"] >= 5 and m["ping"] <= 60 and m["gigue"] <= 30),
    ("Envoi de gros fichiers (sauvegarde en ligne, vidéos)", lambda m: m["montant"] >= 20),
]


# --- La liaison avec la box, lue auprès de Windows (rien n'est envoyé) ---

class _Ipv4(ctypes.Structure):  # sockaddr_in
    _fields_ = [("famille", ctypes.c_short), ("port", ctypes.c_ushort), ("adresse", ctypes.c_ubyte * 4),
                ("zero", ctypes.c_ubyte * 8)]


class _Ipv6(ctypes.Structure):  # sockaddr_in6
    _fields_ = [("famille", ctypes.c_short), ("port", ctypes.c_ushort), ("flux", wintypes.ULONG),
                ("adresse", ctypes.c_ubyte * 16), ("portee", wintypes.ULONG)]


class _Ssid(ctypes.Structure):  # DOT11_SSID
    _fields_ = [("longueur", wintypes.ULONG), ("octets", ctypes.c_ubyte * 32)]


class _Connexion(ctypes.Structure):  # WLAN_CONNECTION_ATTRIBUTES
    _fields_ = [("etat", ctypes.c_int), ("mode", ctypes.c_int), ("profil", wintypes.WCHAR * 256),
                ("ssid", _Ssid), ("type_bss", ctypes.c_int), ("bssid", ctypes.c_ubyte * 6), ("type_phy", ctypes.c_int),
                ("index_phy", wintypes.ULONG), ("qualite", wintypes.ULONG), ("reception", wintypes.ULONG),
                ("emission", wintypes.ULONG), ("securite", wintypes.DWORD * 4)]


WLAN_CONNEXION_ACTUELLE, WLAN_CANAL = 7, 8  # wlan_intf_opcode_current_connection, wlan_intf_opcode_channel_number


def _iphlpapi() -> ctypes.WinDLL:
    iphlpapi = ctypes.WinDLL("iphlpapi")
    iphlpapi.GetBestInterfaceEx.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    iphlpapi.ConvertInterfaceIndexToLuid.argtypes = [wintypes.ULONG, ctypes.POINTER(ctypes.c_uint64)]
    iphlpapi.ConvertInterfaceLuidToAlias.argtypes = [ctypes.POINTER(ctypes.c_uint64), wintypes.LPWSTR, ctypes.c_size_t]
    iphlpapi.ConvertInterfaceLuidToGuid.argtypes = [ctypes.POINTER(ctypes.c_uint64), ctypes.c_void_p]
    return iphlpapi


def interface_internet() -> tuple[str, int, uuid.UUID] | None:
    """(nom, type, GUID) de l'interface par laquelle Windows passerait pour aller sur internet, ou None.

    Windows choisit la route vers une adresse publique de Cloudflare sans rien envoyer : en IPv4, sinon en IPv6
    (réseau sans IPv4). GetBestInterfaceEx renvoie 0 quand il trouve une route.
    """
    iphlpapi = _iphlpapi()
    index = wintypes.DWORD()
    destinations = (_Ipv4(socket.AF_INET, 0, (ctypes.c_ubyte * 4)(1, 1, 1, 1)),
                    _Ipv6(socket.AF_INET6, 0, 0, (ctypes.c_ubyte * 16)(0x26, 0x06, 0x47, 0, 0x47, 0, *[0] * 9, 1)))
    if all(iphlpapi.GetBestInterfaceEx(ctypes.byref(destination), ctypes.byref(index))
           for destination in destinations):  # s'arrête à la première route trouvée
        return None  # aucune route vers internet : le PC n'est relié à aucun réseau
    luid = ctypes.c_uint64()
    nom = ctypes.create_unicode_buffer(257)  # IF_MAX_STRING_SIZE + 1
    guid = (ctypes.c_ubyte * 16)()
    if (iphlpapi.ConvertInterfaceIndexToLuid(index, ctypes.byref(luid))
            or iphlpapi.ConvertInterfaceLuidToAlias(ctypes.byref(luid), nom, len(nom))
            or iphlpapi.ConvertInterfaceLuidToGuid(ctypes.byref(luid), guid)):
        return None
    return nom.value, luid.value >> 48, uuid.UUID(bytes_le=bytes(guid))  # le type est dans les 16 bits du haut


def bande(canal: int, type_phy: int, debit_liaison: float) -> str | None:
    """Bande Wi-Fi d'après le numéro du canal ; None quand on ne peut pas trancher.

    Les canaux du 6 GHz (Wi-Fi 6E et 7 seulement) portent les numéros 1, 5, 9… 233, déjà pris en partie par le
    2,4 GHz (1 à 14) et le 5 GHz (149 à 177). Une liaison au-delà de 600 Mbit/s n'est pas du 2,4 GHz.
    """
    possible_6 = type_phy >= PHY_WIFI_6 and canal % 4 == 1
    if 1 <= canal <= 14:
        return None if possible_6 and debit_liaison > 600 else "2,4 GHz"
    if possible_6:
        return None if 149 <= canal <= 177 else "6 GHz" if canal <= 233 else None
    return "5 GHz" if 32 <= canal <= 177 else None


def norme(type_phy: int, bande_: str | None) -> str | None:
    if type_phy == PHY_WIFI_6 and bande_ == "6 GHz":
        return "Wi-Fi 6E"
    return NORMES.get(type_phy)


def _wlanapi() -> ctypes.WinDLL:
    wlan = ctypes.WinDLL("wlanapi")
    wlan.WlanOpenHandle.argtypes = [wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
                                    ctypes.POINTER(wintypes.HANDLE)]
    wlan.WlanCloseHandle.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    wlan.WlanQueryInterface.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
                                        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.c_void_p),
                                        ctypes.c_void_p]
    wlan.WlanFreeMemory.argtypes = [ctypes.c_void_p]
    return wlan


def _interroger(wlan: ctypes.WinDLL, client: wintypes.HANDLE, guid: ctypes.Array, question: int, structure: type):
    """Réponse de Windows sur l'interface Wi-Fi `guid` (copiée), ou None s'il ne la donne pas."""
    taille, donnees = wintypes.DWORD(), ctypes.c_void_p()
    if wlan.WlanQueryInterface(client, guid, question, None, ctypes.byref(taille), ctypes.byref(donnees), None):
        return None
    try:
        return structure.from_buffer_copy(ctypes.string_at(donnees.value, ctypes.sizeof(structure)))
    finally:
        wlan.WlanFreeMemory(donnees)


def wifi(guid_interface: uuid.UUID) -> dict | None:
    """Signal (en %, celui des barres de Windows), bande et norme du Wi-Fi utilisé ; None si Windows ne les donne pas
    (service Wi-Fi arrêté, accès refusé par la confidentialité de Windows…)."""
    wlan = _wlanapi()
    client, version = wintypes.HANDLE(), wintypes.DWORD()
    if wlan.WlanOpenHandle(2, None, ctypes.byref(version), ctypes.byref(client)):
        return None
    try:
        guid = (ctypes.c_ubyte * 16)(*guid_interface.bytes_le)
        connexion = _interroger(wlan, client, guid, WLAN_CONNEXION_ACTUELLE, _Connexion)
        if connexion is None:
            return None
        canal = _interroger(wlan, client, guid, WLAN_CANAL, ctypes.c_ulong)
        bande_ = bande(canal.value, connexion.type_phy, connexion.reception / 1000) if canal else None
        return {"signal": connexion.qualite, "bande": bande_, "norme": norme(connexion.type_phy, bande_)}
    finally:
        wlan.WlanCloseHandle(client, None)


def liaison() -> dict:
    """La liaison du PC avec la box, d'après Windows : type (« wifi », « cable », « mobile », « autre », ou None sans
    réseau), nom de l'interface, vitesse de la liaison (Mbit/s) et, en Wi-Fi, signal, bande et norme."""
    interface = interface_internet()
    if interface is None:
        return {"type": None, "nom": None, "vitesse": None, "wifi": None}
    nom, type_, guid = interface
    type_ = TYPES.get(type_, "autre")
    statistiques = psutil.net_if_stats().get(nom)
    return {"type": type_, "nom": nom, "vitesse": statistiques.speed if statistiques and statistiques.speed else None,
            "wifi": wifi(guid) if type_ == "wifi" else None}


# --- Le test (seule partie qui utilise le réseau, sur clic) ---

def adresse_serveur() -> tuple[int, tuple]:
    famille, _type, _protocole, _nom, adresse = socket.getaddrinfo(SERVEUR, PORT, type=socket.SOCK_STREAM)[0]
    return famille, adresse


def mesurer_ping(progression: Callable[[float, float | None], None], arret: Callable[[], bool]) -> list[float] | None:
    """Durées (ms) d'ouverture d'une connexion avec le serveur : un aller-retour sur le réseau, comme un ping.

    `progression(avance, ping)` après chaque mesure. None si `arret()` devient vrai.
    """
    famille, adresse = adresse_serveur()
    durees = []
    for numero in range(NB_PINGS):
        if arret():
            return None
        with socket.socket(famille, socket.SOCK_STREAM) as connexion:
            connexion.settimeout(DELAI)
            debut = time.perf_counter()
            connexion.connect(adresse)
            durees.append((time.perf_counter() - debut) * 1000)
        progression((numero + 1) / NB_PINGS, statistics.median(durees))
        time.sleep(ECART_PINGS)
    return durees


def gigue(durees: list[float]) -> float:
    """Variation moyenne d'un ping au suivant (ms) : une connexion irrégulière gêne les jeux et les appels vidéo."""
    return statistics.fmean(abs(a - b) for a, b in zip(durees, durees[1:])) if len(durees) > 1 else 0.0


class Refus(ConnectionError):
    """Le serveur de test refuse la mesure : trop de tests depuis cette connexion, le plus souvent."""

    def __init__(self, statut: int, attente: str | None) -> None:
        super().__init__(f"Réponse du serveur de test : {statut} (attendre : {attente} s)")
        self.attente = int(attente) if attente and attente.isdigit() else None  # en secondes


def _verifier(reponse: http.client.HTTPResponse) -> None:
    if reponse.status != 200:
        raise Refus(reponse.status, reponse.getheader("Retry-After"))


def telecharger(octets: list[int], numero: int, fini: Callable[[], bool], contexte: ssl.SSLContext) -> None:
    """Un flux de téléchargement : demande des données de test jusqu'à `fini()`, en comptant les octets reçus."""
    connexion = http.client.HTTPSConnection(SERVEUR, timeout=DELAI, context=contexte)
    tampon = memoryview(bytearray(BLOC))
    try:
        while not fini():
            connexion.request("GET", f"/__down?bytes={TAILLE_REQUETE['descendant']}", headers=ENTETES)
            reponse = connexion.getresponse()
            _verifier(reponse)
            while not fini() and (lus := reponse.readinto(tampon)):
                octets[numero] += lus
    finally:
        connexion.close()  # une réponse interrompue ne se reprend pas : la connexion est fermée


def envoyer(octets: list[int], numero: int, fini: Callable[[], bool], contexte: ssl.SSLContext) -> None:
    """Un flux d'envoi : envoie des données tirées au hasard jusqu'à `fini()`, en comptant les octets partis."""
    connexion = http.client.HTTPSConnection(SERVEUR, timeout=DELAI, context=contexte)
    morceau = os.urandom(BLOC)
    nombre = TAILLE_REQUETE["montant"] // BLOC
    entetes = ENTETES | {"Content-Type": "application/octet-stream", "Content-Length": str(nombre * BLOC)}

    def corps():
        for _ in range(nombre):
            if fini():
                return
            yield morceau
            octets[numero] += BLOC  # reprend ici une fois le morceau parti

    try:
        while not fini():
            connexion.request("POST", "/__up", body=corps(), headers=entetes)
            if fini():
                break  # envoi interrompu : la réponse n'arrivera pas
            reponse = connexion.getresponse()
            _verifier(reponse)
            reponse.read()
    finally:
        connexion.close()


Flux = Callable[[list[int], int, Callable[[], bool]], None]


def debit_stable(releves: list[tuple[float, int]]) -> float | None:
    """Débit (Mbit/s) d'après des relevés (instant, octets passés depuis le début), sans les premiers PART_CHAUFFE
    des données, où le débit monte encore en puissance (sauf si la mesure a été trop courte pour ça)."""
    fin, total = releves[-1]
    depart, octets = next((releve for releve in releves if releve[1] >= PART_CHAUFFE * total), releves[0])
    if fin - depart < 0.5:
        depart, octets = releves[0]
    return (total - octets) * 8 / (fin - depart) / 1e6 if total and fin > depart else None


def mesurer_debit(flux: Flux, limite: int, progression: Callable[[float, float | None], None],
                  arret: Callable[[], bool]) -> float | None:
    """Débit (Mbit/s) de FLUX connexions en même temps, pendant DUREE_MESURE secondes, ou moins une fois `limite`
    octets passés.

    `progression(avance, debit)` dix fois par seconde : part de la mesure faite (0 à 1) et débit jusque-là.
    None si `arret()` devient vrai. Si une connexion échoue, la mesure aussi : avec moins de connexions, elle
    serait trop basse.
    """
    octets = [0] * FLUX  # chaque flux compte dans sa case : pas besoin de verrou
    fini = threading.Event()
    erreurs: list[Exception] = []

    def lancer(numero: int) -> None:
        try:
            flux(octets, numero, fini.is_set)
        except Exception as erreur:
            if not fini.is_set():
                erreurs.append(erreur)

    fils = [threading.Thread(target=lancer, args=(numero,), daemon=True, name=f"debit-{numero}")
            for numero in range(FLUX)]
    debut = time.perf_counter()
    releves = [(debut, 0)]
    for fil in fils:
        fil.start()
    try:
        while not arret() and not erreurs:
            time.sleep(0.1)
            maintenant, total = time.perf_counter(), sum(octets)
            releves.append((maintenant, total))
            progression(min(1.0, max((maintenant - debut) / DUREE_MESURE, total / limite)), debit_stable(releves))
            if maintenant - debut >= DUREE_MESURE or total >= limite or not any(fil.is_alive() for fil in fils):
                break
    finally:
        fini.set()  # les flux s'arrêtent au bloc suivant ; un flux bloqué abandonne au bout de DELAI
    if arret():
        return None
    if erreurs:
        raise erreurs[0]
    debit = debit_stable(releves)
    if debit is None:
        raise ConnectionError("Aucune donnée n'est passée pendant le test")
    return debit


def trafic(nom: str | None) -> tuple[float, int] | None:
    """(instant, octets reçus et envoyés jusque-là) par l'interface `nom`, pour mesurer ce qui passe déjà."""
    compteurs = psutil.net_io_counters(pernic=True).get(nom) if nom else None
    return (time.perf_counter(), compteurs.bytes_recv + compteurs.bytes_sent) if compteurs else None


def debit_entre(avant: tuple[float, int] | None, apres: tuple[float, int] | None) -> float:
    """Débit moyen (Mbit/s) entre deux relevés de `trafic`."""
    if not avant or not apres or apres[0] <= avant[0]:
        return 0.0
    return max(0, apres[1] - avant[1]) * 8 / (apres[0] - avant[0]) / 1e6


def scan(progression: Callable[[str, float, float | None], None] = lambda *_: None,
         arret: Callable[[], bool] = lambda: False) -> dict | None:
    """Teste la connexion : ping, puis débit descendant (téléchargement) et montant (envoi).

    `progression(etape, avance, valeur)` : étape « ping », « descendant » ou « montant », part faite (0 à 1) et
    valeur du moment (ms ou Mbit/s, None tant qu'elle n'est pas connue). None si `arret()` devient vrai.
    Sans réseau ou sans réponse du serveur : {"liaison": ..., "erreur": explication}.
    """
    debut = time.perf_counter()
    lien = liaison()
    if lien["type"] is None:
        return {"liaison": lien, "erreur": "Ton PC n'est relié à aucun réseau : active le Wi-Fi ou branche un "
                                           "câble, puis relance le test."}
    contexte = ssl.create_default_context()
    try:
        avant = trafic(lien["nom"])  # pendant les pings, la connexion est presque au repos
        durees = mesurer_ping(lambda avance, ping: progression("ping", avance, ping), arret)
        deja = debit_entre(avant, trafic(lien["nom"]))
        if durees is None:
            return None
        mesures = {"ping": statistics.median(durees), "gigue": gigue(durees)}
        for sens, flux in (("descendant", telecharger), ("montant", envoyer)):
            debit = mesurer_debit(lambda octets, numero, fini: flux(octets, numero, fini, contexte), LIMITE[sens],
                                  lambda avance, valeur, sens=sens: progression(sens, avance, valeur), arret)
            if debit is None:
                return None
            mesures[sens] = debit
    except Refus as refus:
        journal.warning("Test de connexion refusé par le serveur : %s", refus)
        return {"liaison": lien, "erreur": "Le serveur de test de Cloudflare refuse les tests trop rapprochés depuis "
                                           f"une même connexion : réessaie {delai_lisible(refus.attente)}."}
    except (OSError, http.client.HTTPException):  # erreurs de réseau, certificat refusé compris
        journal.exception("Test de connexion impossible")
        return {"liaison": lien, "erreur": "Le serveur de test n'a pas répondu : internet ne passe pas sur ce réseau "
                                           "en ce moment (box déconnectée, page de connexion d'un hôtel ou d'une "
                                           "gare, pare-feu…). Si ça dure, redémarre la box."}
    resultat = {"liaison": lien, **mesures, "trafic": deja, "duree": time.perf_counter() - debut,
                "date": datetime.now()}
    resultat |= {"usages": [(usage, condition(mesures)) for usage, condition in USAGES],
                 "conseils": conseils(resultat)}
    journal.info("Test de connexion : ping %.0f ms, %.1f Mbit/s en téléchargement, %.1f Mbit/s en envoi (%s)",
                 mesures["ping"], mesures["descendant"], mesures["montant"], lien["type"])
    return resultat


# --- Ce que le test veut dire, en français simple ---

def nombre_debit(debit: float) -> str:
    """« 4,6 », « 212 », « 1 201 » (Mbit/s)."""
    if debit < 10:
        return f"{debit:.1f}".replace(".", ",")
    return f"{debit:,.0f}".replace(",", "\u202f")


def delai_lisible(secondes: int | None) -> str:
    """« dans une heure environ », « dans 5 minutes »… d'après l'attente demandée par le serveur."""
    if secondes is None:
        return "dans un moment"
    if secondes >= 45 * 60:
        heures = round(secondes / 3600)
        return "dans une heure environ" if heures <= 1 else f"dans {heures} heures environ"
    minutes = max(1, round(secondes / 60))
    return "dans une minute" if minutes == 1 else f"dans {minutes} minutes"


def mot_signal(signal: int) -> str:
    return "excellent" if signal >= 80 else "bon" if signal >= 60 else "moyen" if signal >= 40 else "faible"


def description(lien: dict) -> list[tuple[str, str, str]]:
    """Lignes de « Ta liaison avec la box » : (nom, valeur, précision éventuelle)."""
    if lien["type"] is None:
        return [("Connexion", "Aucune", "Le PC n'est relié à aucun réseau : active le Wi-Fi ou branche un câble.")]
    lignes = [("Connexion", NOMS_TYPES[lien["type"]], "")]
    wifi_ = lien["wifi"]
    if wifi_:
        lignes.append(("Signal Wi-Fi", f"{wifi_['signal']} % ({mot_signal(wifi_['signal'])})", ""))
        genre = " · ".join(texte for texte in (wifi_["bande"], wifi_["norme"]) if texte)
        if genre:
            lignes.append(("Type de Wi-Fi", genre, ""))
    if lien["vitesse"]:
        lignes.append(("Vitesse de la liaison", f"{nombre_debit(lien['vitesse'])} Mbit/s",
                       "Le maximum possible entre le PC et la box, pas la vitesse d'internet."))
    return lignes


def niveau(resultat: dict) -> tuple[str, str, str]:
    """(couleur, mot, phrase) d'après le débit de téléchargement, celui qui compte le plus au quotidien."""
    debit = resultat["descendant"]
    if debit < 8:
        return "rouge", "Lente", "Ta connexion est lente : les pages et les vidéos risquent de charger lentement."
    if debit < 30:
        return ("orange", "Correcte", "Ta connexion suffit pour le web et la vidéo en HD, mais elle peut saturer "
                                      "avec plusieurs appareils à la fois.")
    if debit < 100:
        return "vert", "Rapide", "Ta connexion est rapide : vidéo en 4K et gros téléchargements passent sans souci."
    return "vert", "Très rapide", "Ta connexion est très rapide : de quoi tout faire, même à plusieurs à la fois."


def conseils(resultat: dict) -> list[tuple[str, tuple[str, str] | None]]:
    """Ce qui ralentit la connexion et comment y remédier : (texte, lien vers les Paramètres ou None), du plus utile
    au moins utile, trois au plus."""
    lien, wifi_ = resultat["liaison"], resultat["liaison"]["wifi"]
    descendant, ping = resultat["descendant"], resultat["ping"]
    # Le débit atteint la moitié de la vitesse de la liaison (son maximum réel) : c'est la liaison qui limite.
    liaison_saturee = bool(lien["vitesse"]) and descendant >= lien["vitesse"] / 2
    trouves = []
    if wifi_ and wifi_["signal"] < 40:
        trouves.append((f"Le signal Wi-Fi est faible ({wifi_['signal']} %) : rapproche le PC de la box, ou dégage ce "
                        "qui les sépare (murs épais, étages, meuble en métal). Un câble réseau donne toujours le "
                        "meilleur débit.", None))
    elif lien["type"] == "wifi" and liaison_saturee and lien["vitesse"] < 300:
        trouves.append((f"La liaison Wi-Fi entre le PC et la box plafonne à {nombre_debit(lien['vitesse'])} Mbit/s : "
                        "c'est elle qui limite le débit. Rapproche-toi de la box, ou branche un câble réseau pour "
                        "profiter de tout ton abonnement.", None))
    if wifi_ and wifi_["bande"] == "2,4 GHz":
        trouves.append(("Ton PC est connecté au Wi-Fi en 2,4 GHz : cette bande porte loin mais va moins vite. Si ta "
                        "box propose aussi un réseau en 5 GHz (souvent le même nom, suivi de « 5G »), choisis-le "
                        "quand tu es près de la box.", LIEN_WIFI))
    if ping > 100 or resultat["gigue"] > 30:
        trouves.append((f"La connexion met du temps à réagir (ping de {ping:.0f} ms, variations de "
                        f"{resultat['gigue']:.0f} ms) : gênant pour les jeux en ligne et les appels vidéo. C'est "
                        "normal en 4G ou par satellite ; sinon, vérifie qu'aucun autre appareil ne télécharge en même "
                        "temps, puis redémarre la box.", None))
    bonne_liaison = lien["type"] == "cable" or (wifi_ and wifi_["signal"] >= 60)
    if descendant < 10 and bonne_liaison and not liaison_saturee:
        trouves.append(("Le débit est faible alors que la liaison avec la box est bonne : le ralentissement vient de "
                        "la box ou de l'abonnement. Redémarre la box ; si rien ne change, compare avec le débit promis "
                        "par ton fournisseur d'accès et contacte-le.", None))
    return trouves[:3]


def remarque(resultat: dict) -> str | None:
    """Mise en garde sur la mesure elle-même : d'autres programmes utilisaient déjà la connexion."""
    if resultat["trafic"] < SEUIL_TRAFIC:
        return None
    return (f"D'autres programmes utilisaient déjà la connexion au début du test (environ "
            f"{nombre_debit(resultat['trafic'])} Mbit/s : mise à jour, jeu qui se télécharge, vidéo…) : le vrai débit "
            "est sans doute un peu plus élevé. Relance le test une fois ces téléchargements finis.")
