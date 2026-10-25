"""Mises à jour : signale une nouvelle version publiée sur GitHub et l'installe sur demande.

Au lancement, une seule requête demande à GitHub la liste des versions publiées : elle ne contient que le nom de
l'application et sa version, rien sur le PC ni sur l'utilisateur. L'installation se fait seulement sur clic : le zip
de la nouvelle version est téléchargé depuis GitHub, vérifié (taille et empreinte SHA-256 données par GitHub), puis
décompressé dans le dossier de l'application. L'application se ferme, la nouvelle version (lancée en mode
installation) remplace l'ancienne, gardée de côté et remise en place en cas d'échec, puis rouvre l'application.
Rien d'autre n'est modifié : l'historique et les réglages sont dans %LOCALAPPDATA%, pas dans ce dossier.
"""

import hashlib
import http.client
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

import psutil

import config

journal = logging.getLogger(__name__)

DEPOT = "MonsieurPlot1/bilan-sante-pc"
API = f"https://api.github.com/repos/{DEPOT}/releases?per_page=20"  # les plus récentes d'abord
PAGE = f"https://github.com/{DEPOT}/releases"
ORIGINE_ZIP = f"https://github.com/{DEPOT}/releases/download/"
ENTETES = {"User-Agent": f"BilanSantePC/{config.VERSION}", "Accept": "application/vnd.github+json"}
DELAI = 15  # secondes sans réponse de GitHub avant d'abandonner

SUFFIXE_ZIP = "-windows.zip"  # BilanSantePC-vX.Y.Z-windows.zip, joint à chaque version publiée
DOSSIER_ZIP = "BilanSantePC"  # dossier de l'application, à la racine du zip
NOM_EXE = "BilanSantePC.exe"
TAILLE_MAX = 500 * 1024**2  # zip ou contenu décompressé : au-delà, ce n'est pas l'application
BLOC = 256 * 1024

# Dans le dossier de l'application, le temps d'une mise à jour (effacés au lancement suivant).
TEMPORAIRE = ".mise-a-jour"  # nouvelle version décompressée
ANCIENNE = ".ancienne-version"  # ancienne version, gardée de côté pendant le remplacement
ATTENTE_FERMETURE = 120  # secondes au plus pour que l'ancienne version se ferme (fin d'une analyse comprise)
ESSAIS = 10  # un fichier tout juste libéré peut rester bloqué un instant (antivirus) : on réessaie
PAUSE = 0.5

ARGUMENT_INSTALLER = "--installer"  # BilanSantePC.exe --installer <dossier de l'application> <pid de l'ancienne>
ARGUMENT_FAITE = "--mise-a-jour-faite"
ARGUMENT_RATEE = "--mise-a-jour-ratee"


class Invalide(ValueError):
    """Le fichier téléchargé n'est pas celui publié, ou ne contient pas l'application."""


def numero(version: str) -> tuple[int, ...] | None:
    """(0, 3, 8) pour « v0.3.8 » ou « 0.3.8 » ; None si ce n'est pas un numéro de version."""
    morceaux = version.removeprefix("v").split(".")
    if not all(morceau.isascii() and morceau.isdigit() for morceau in morceaux):
        return None
    return tuple(int(morceau) for morceau in morceaux)


def zip_de(version: dict) -> dict | None:
    """Le zip de l'application joint à une version publiée, avec son empreinte (sans elle, pas d'installation)."""
    for fichier in version.get("assets") or []:
        empreinte, url = fichier.get("digest") or "", fichier.get("browser_download_url") or ""
        if (fichier.get("name", "").endswith(SUFFIXE_ZIP) and empreinte.startswith("sha256:")
                and url.startswith(ORIGINE_ZIP)):
            return {"nom": Path(fichier["name"]).name, "url": url, "taille": int(fichier["size"]),
                    "empreinte": empreinte.removeprefix("sha256:").lower()}
    return None


def plus_recente(versions: list[dict], actuelle: str = config.VERSION) -> dict | None:
    """La version publiée la plus récente, si elle est plus récente que `actuelle` ; sinon None.

    Les préversions comptent (toutes les versions de test en sont), les brouillons jamais.
    """
    publiees = [(numero_, version) for version in versions
                if not version.get("draft") and (numero_ := numero(version.get("tag_name") or ""))]
    if not publiees:
        return None
    numero_, version = max(publiees, key=lambda publiee: publiee[0])
    if numero_ <= numero(actuelle):
        return None
    return {"version": version["tag_name"].removeprefix("v"), "notes": (version.get("body") or "").strip(),
            "page": version.get("html_url") or PAGE, "zip": zip_de(version)}


def notes_lisibles(notes: str, longueur_max: int = 600) -> str:
    """Les nouveautés (entrée du journal des versions) en puces, sans les retours à la ligne du fichier."""
    points: list[str] = []
    for ligne in notes.splitlines():
        ligne = ligne.strip()
        if ligne.startswith(("- ", "* ")):
            points.append(ligne[2:])
        elif ligne and points:
            points[-1] += " " + ligne  # suite du point précédent
        elif ligne:
            points.append(ligne)
    texte = "\n".join(f"• {point}" for point in points)
    return texte if len(texte) <= longueur_max else texte[:longueur_max].rsplit(" ", 1)[0] + "…"


def _ouvrir(url: str):
    """Réponse HTTPS de GitHub (redirections suivies : les fichiers joints sont servis par un autre serveur)."""
    return urllib.request.urlopen(urllib.request.Request(url, headers=ENTETES), timeout=DELAI)


def chercher() -> dict | None:
    """La nouvelle version publiée sur GitHub, ou None : déjà à jour, hors ligne, GitHub injoignable…"""
    try:
        with _ouvrir(API) as reponse:
            nouvelle = plus_recente(json.load(reponse))
    except (OSError, http.client.HTTPException, ValueError, KeyError, TypeError, AttributeError):
        journal.warning("Recherche de mise à jour impossible", exc_info=True)  # hors ligne : rien à signaler
        return None
    if nouvelle:
        journal.info("Nouvelle version disponible : %s", nouvelle["version"])
    return nouvelle


def dossier_application() -> Path | None:
    """Dossier de l'application installée (celui du .exe) ; None quand elle tourne depuis le code source."""
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else None


def installable(nouvelle: dict, dossier: Path | None = None) -> bool:
    """Vrai si la nouvelle version peut s'installer toute seule : application installée, zip publié, et dossier
    où l'application a le droit d'écrire (pas dans « Program Files », par exemple)."""
    dossier = dossier or dossier_application()
    if dossier is None or nouvelle["zip"] is None:
        return False
    essai = dossier / f".essai-{os.getpid()}"
    try:  # os.access ne voit pas les droits de Windows : seul un vrai essai le dit
        essai.touch()
        essai.unlink()
    except OSError:
        return False
    return True


def verifier() -> dict | None:
    """Au lancement : efface ce qui reste d'une mise à jour, puis cherche une nouvelle version."""
    nettoyer()
    return chercher()


def telecharger(fichier: dict, destination: Path, progression: Callable[[float], None],
                arret: Callable[[], bool]) -> Path | None:
    """Télécharge le zip `fichier` (voir zip_de) dans `destination`, en vérifiant sa taille et son empreinte.

    `progression(part)` : part téléchargée (0 à 1). None si `arret()` devient vrai.
    """
    if not fichier["url"].startswith(ORIGINE_ZIP) or not 0 < fichier["taille"] <= TAILLE_MAX:
        raise Invalide(f"Fichier inattendu : {fichier['url']} ({fichier['taille']} octets)")
    chemin = destination / fichier["nom"]
    empreinte, recus = hashlib.sha256(), 0
    with _ouvrir(fichier["url"]) as reponse, open(chemin, "wb") as sortie:
        while bloc := reponse.read(BLOC):
            if arret():
                return None
            recus += len(bloc)
            if recus > fichier["taille"]:
                raise Invalide("Le fichier téléchargé est plus gros que celui publié")
            empreinte.update(bloc)
            sortie.write(bloc)
            progression(recus / fichier["taille"])
    if recus != fichier["taille"] or empreinte.hexdigest() != fichier["empreinte"]:
        raise Invalide("Le fichier téléchargé ne correspond pas à celui publié")
    return chemin


def decompresser(archive: Path, destination: Path) -> Path:
    """Décompresse le zip dans `destination` ; renvoie le dossier de la nouvelle version (celui de son .exe)."""
    with zipfile.ZipFile(archive) as contenu:
        if sum(element.file_size for element in contenu.infolist()) > TAILLE_MAX:
            raise Invalide("Le zip décompressé serait trop gros")
        contenu.extractall(destination)  # zipfile n'écrit jamais hors de `destination` (chemins « .. » écartés)
    dossier = destination / DOSSIER_ZIP
    if not (dossier / NOM_EXE).is_file():
        raise Invalide("Le zip ne contient pas l'application")
    return dossier


def preparer(fichier: dict, dossier_app: Path, progression: Callable[[float], None],
             arret: Callable[[], bool]) -> Path | None:
    """Télécharge et décompresse la nouvelle version dans le dossier temporaire de l'application.

    Renvoie le .exe de la nouvelle version, prêt à s'installer ; None si `arret()` devient vrai.
    """
    temporaire = dossier_app / TEMPORAIRE
    shutil.rmtree(temporaire, ignore_errors=True)
    temporaire.mkdir()
    try:
        archive = telecharger(fichier, temporaire, progression, arret)
        if archive is None:
            shutil.rmtree(temporaire, ignore_errors=True)
            return None
        nouvelle = decompresser(archive, temporaire)
        archive.unlink()
    except BaseException:
        shutil.rmtree(temporaire, ignore_errors=True)
        raise
    return nouvelle / NOM_EXE


def _environnement() -> dict[str, str]:
    """Variables d'environnement pour lancer une autre copie de l'application, sans celles de la copie actuelle
    (dossier de ses bibliothèques en tête du PATH, extensions de Qt) : elle démarre comme lancée d'un double-clic."""
    environnement = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    for variable in ("QT_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        environnement.pop(variable, None)
    interne = getattr(sys, "_MEIPASS", None)
    if interne:
        environnement["PATH"] = os.pathsep.join(chemin for chemin in environnement.get("PATH", "").split(os.pathsep)
                                                if chemin != interne)
    return environnement


def _lancer(arguments: list[str], dossier: Path) -> None:
    """Lance un .exe de l'application, détaché : il continue après la fermeture de celle-ci."""
    subprocess.Popen(arguments, cwd=dossier, env=_environnement(), close_fds=True,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)


def lancer_installation(exe: Path, dossier_app: Path) -> None:
    """Lance la nouvelle version en mode installation : elle attend que l'application se ferme pour la remplacer."""
    _lancer([str(exe), ARGUMENT_INSTALLER, str(dossier_app), str(os.getpid())], exe.parent)


def attendre_fermeture(pid: int, delai: float = ATTENTE_FERMETURE) -> bool:
    """Attend la fin du processus `pid` (l'ancienne version) ; faux s'il tourne encore au bout de `delai` s."""
    try:
        psutil.Process(pid).wait(timeout=delai)
    except psutil.NoSuchProcess:
        pass
    except psutil.TimeoutExpired:
        return False
    return True


def _reessayer(action: Callable[[], object]) -> None:
    for essai in range(ESSAIS):
        try:
            action()
            return
        except OSError:
            if essai == ESSAIS - 1:
                raise
            time.sleep(PAUSE)


def _effacer(chemin: Path) -> None:
    if chemin.is_dir():
        shutil.rmtree(chemin, ignore_errors=True)
    else:
        chemin.unlink(missing_ok=True)


def remplacer(source: Path, dossier_app: Path) -> bool:
    """Remplace les fichiers de l'application par ceux de `source` (la nouvelle version).

    L'ancienne version est d'abord mise de côté dans ANCIENNE : en cas d'échec, elle est remise en place.
    """
    ancienne = dossier_app / ANCIENNE
    shutil.rmtree(ancienne, ignore_errors=True)
    ancienne.mkdir()
    mis_de_cote: list[str] = []
    copies: list[Path] = []
    try:
        for element in sorted(source.iterdir()):
            cible = dossier_app / element.name
            if cible.exists():
                _reessayer(lambda: cible.rename(ancienne / element.name))
                mis_de_cote.append(element.name)
            copies.append(cible)  # avant la copie : une copie à moitié faite est effacée aussi
            if element.is_dir():
                shutil.copytree(element, cible)
            else:
                shutil.copy2(element, cible)
    except OSError:
        journal.exception("Installation de la mise à jour impossible : retour à l'ancienne version")
        for cible in copies:
            _effacer(cible)
        for nom in mis_de_cote:
            _reessayer(lambda: (ancienne / nom).rename(dossier_app / nom))
        return False
    return True


def installer(dossier_app: Path, pid: int) -> bool:
    """Mode installation, dans la nouvelle version lancée depuis le dossier temporaire : attend la fermeture de
    l'ancienne, la remplace, puis rouvre l'application (l'ancienne version si le remplacement a échoué)."""
    source = Path(sys.executable).parent
    # Garde-fou : seulement le dossier d'une application installée, depuis son propre dossier temporaire.
    if (source.resolve().parent != (dossier_app / TEMPORAIRE).resolve()
            or not (dossier_app / NOM_EXE).is_file()):
        journal.error("Installation refusée : %s n'est pas la mise à jour de %s", source, dossier_app)
        return False
    if not attendre_fermeture(pid):
        journal.error("Installation abandonnée : l'ancienne version ne s'est pas fermée")
        return False
    faite = remplacer(source, dossier_app)
    journal.info("Mise à jour installée" if faite else "Mise à jour annulée")
    _lancer([str(dossier_app / NOM_EXE), ARGUMENT_FAITE if faite else ARGUMENT_RATEE], dossier_app)
    return faite


def installer_depuis(arguments: list[str]) -> int:
    """`BilanSantePC.exe --installer <dossier> <pid>` : code de sortie 0 si la mise à jour est installée."""
    try:
        position = arguments.index(ARGUMENT_INSTALLER)
        dossier, pid = Path(arguments[position + 1]), int(arguments[position + 2])
    except (ValueError, IndexError):
        journal.error("Mode installation : arguments invalides %s", arguments)
        return 1
    return 0 if installer(dossier, pid) else 1


def nettoyer(dossier_app: Path | None = None) -> None:
    """Efface ce qui reste d'une mise à jour (nouvelle version décompressée, ancienne version mise de côté).

    Au lancement qui suit une mise à jour, le mode installation se termine à peine : on réessaie un instant.
    """
    dossier = dossier_app or dossier_application()
    if dossier is None:
        return  # depuis le code source : jamais rien d'effacé
    for nom in (TEMPORAIRE, ANCIENNE):
        chemin = dossier / nom
        for _ in range(ESSAIS):
            if not chemin.exists():
                break
            shutil.rmtree(chemin, ignore_errors=True)
            if chemin.exists():
                time.sleep(PAUSE)
