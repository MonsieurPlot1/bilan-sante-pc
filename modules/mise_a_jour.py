"""Mises à jour : signale une nouvelle version publiée sur GitHub et l'installe sur demande.

Au lancement, une seule requête demande à GitHub la liste des versions publiées : elle ne contient que le nom de
l'application et sa version, rien sur le PC ni sur l'utilisateur. L'installation se fait seulement sur clic :
l'installateur de la nouvelle version (installateur.iss) est téléchargé depuis GitHub dans le dossier de l'application,
vérifié (taille et empreinte SHA-256 données par GitHub), puis lancé sans questions. L'application se ferme,
l'installateur la remplace dans son dossier, puis la rouvre (même en cas d'échec, pour le signaler).
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
from pathlib import Path
from typing import Callable

import psutil

import config

journal = logging.getLogger(__name__)

DEPOT = "MonsieurPlot1/bilan-sante-pc"
API = f"https://api.github.com/repos/{DEPOT}/releases?per_page=20"  # les plus récentes d'abord
PAGE = f"https://github.com/{DEPOT}/releases"
ORIGINE = f"https://github.com/{DEPOT}/releases/download/"  # seule adresse d'où un fichier est téléchargé
ENTETES = {"User-Agent": f"BilanSantePC/{config.VERSION}", "Accept": "application/vnd.github+json"}
DELAI = 15  # secondes sans réponse de GitHub avant d'abandonner

PREFIXE_INSTALLATEUR = "BilanSantePC-Installation-"  # BilanSantePC-Installation-vX.Y.Z.exe, joint à chaque version
NOM_EXE = "BilanSantePC.exe"
TAILLE_MAX = 500 * 1024**2  # au-delà, ce n'est pas l'application
BLOC = 256 * 1024

# Dans le dossier de l'application, le temps d'une mise à jour (effacés au lancement suivant).
TEMPORAIRE = ".mise-a-jour"  # installateur téléchargé
ANCIENNE = ".ancienne-version"  # ancienne version, gardée de côté pendant le remplacement (installateur.iss aussi)
ATTENTE_FERMETURE = 120  # secondes au plus pour que l'ancienne version se ferme (fin d'une analyse comprise)
ESSAIS = 10  # un fichier tout juste libéré peut rester bloqué un instant (antivirus) : on réessaie
PAUSE = 0.5

# Installateur lancé sans questions (seulement sa barre de progression) ; il attend la fin du processus /ATTENDRE.
OPTIONS_INSTALLATEUR = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
ARGUMENT_FAITE = "--mise-a-jour-faite"  # donnés par l'installateur en rouvrant l'application
ARGUMENT_RATEE = "--mise-a-jour-ratee"
ARGUMENT_INSTALLER = "--installer"  # ancien mode : BilanSantePC.exe --installer <dossier de l'application> <pid>


class Invalide(ValueError):
    """Le fichier téléchargé n'est pas celui publié, ou ne contient pas l'application."""


def numero(version: str) -> tuple[int, ...] | None:
    """(0, 3, 8) pour « v0.3.8 » ou « 0.3.8 » ; None si ce n'est pas un numéro de version."""
    morceaux = version.removeprefix("v").split(".")
    if not all(morceau.isascii() and morceau.isdigit() for morceau in morceaux):
        return None
    return tuple(int(morceau) for morceau in morceaux)


def installateur_de(version: dict) -> dict | None:
    """L'installateur joint à une version publiée, avec son empreinte (sans elle, pas d'installation)."""
    for fichier in version.get("assets") or []:
        nom, empreinte, url = (fichier.get(cle) or "" for cle in ("name", "digest", "browser_download_url"))
        if (nom.startswith(PREFIXE_INSTALLATEUR) and nom.endswith(".exe") and empreinte.startswith("sha256:")
                and url.startswith(ORIGINE)):
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
            "page": version.get("html_url") or PAGE, "installateur": installateur_de(version)}


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
    """Vrai si la nouvelle version peut s'installer toute seule : application installée, installateur publié, et
    dossier où l'application a le droit d'écrire (pas dans « Program Files », par exemple)."""
    dossier = dossier or dossier_application()
    if dossier is None or nouvelle["installateur"] is None:
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
    """Télécharge `fichier` (voir installateur_de) dans `destination`, en vérifiant sa taille et son empreinte.

    `progression(part)` : part téléchargée (0 à 1). None si `arret()` devient vrai.
    """
    if not fichier["url"].startswith(ORIGINE) or not 0 < fichier["taille"] <= TAILLE_MAX:
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


def preparer(fichier: dict, dossier_app: Path, progression: Callable[[float], None],
             arret: Callable[[], bool]) -> Path | None:
    """Télécharge l'installateur de la nouvelle version dans le dossier temporaire de l'application.

    Renvoie l'installateur, vérifié et prêt à être lancé ; None si `arret()` devient vrai.
    """
    temporaire = dossier_app / TEMPORAIRE
    shutil.rmtree(temporaire, ignore_errors=True)
    temporaire.mkdir()
    try:
        installateur = telecharger(fichier, temporaire, progression, arret)
    except BaseException:
        shutil.rmtree(temporaire, ignore_errors=True)
        raise
    if installateur is None:
        shutil.rmtree(temporaire, ignore_errors=True)
    return installateur


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
    """Lance un .exe (installateur ou application), détaché : il continue après la fermeture de l'application."""
    subprocess.Popen(arguments, cwd=dossier, env=_environnement(), close_fds=True,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)


def lancer_installation(installateur: Path, dossier_app: Path) -> None:
    """Lance l'installateur : il attend que l'application se ferme, la remplace dans son dossier, puis la rouvre."""
    _lancer([str(installateur), *OPTIONS_INSTALLATEUR, f"/DIR={dossier_app}", f"/ATTENDRE={os.getpid()}"],
            installateur.parent)


# --- Ancien mode d'installation, gardé pour une version seulement ---
# Jusqu'à la v0.4.1, l'application téléchargeait un zip et lançait la nouvelle version qu'il contenait avec
# `--installer` : c'est ce mode qui remplace alors l'ancienne. La première version publiée avec un installateur garde
# aussi son zip, pour que ces versions puissent s'y mettre à jour ; la suivante pourra retirer ce mode.


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
