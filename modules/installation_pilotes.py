"""Installation des pilotes, seulement sur clic et après confirmation (bouton « Mettre à jour les pilotes »).

1. Le pilote NVIDIA, s'il y en a un plus récent, est téléchargé depuis le site de NVIDIA (dans le dossier de
   l'application, %LOCALAPPDATA%\\BilanSantePC\\pilotes).
2. PowerShell est lancé en administrateur (Windows demande l'autorisation) : il installe les pilotes choisis de
   Windows Update, puis le pilote NVIDIA, après avoir vérifié qu'il est bien signé par NVIDIA. Il note où il en est
   dans un fichier que l'application lit, puis son résultat.
Rien d'autre n'est installé ni modifié. Aucun point de restauration n'est créé (à la demande de l'utilisateur).
"""

import base64
import ctypes
import json
import logging
import re
import shutil
import urllib.request
from ctypes import wintypes
from pathlib import Path
from typing import Callable

from journal import dossier_par_defaut
from modules import pilotes

journal = logging.getLogger(__name__)

TAILLE_MAX = 3 * 1024**3  # au-delà, ce n'est pas un pilote graphique
BLOC = 1024**2
ID_WINDOWS_UPDATE = re.compile(r"^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
SEE_MASK_NOCLOSEPROCESS, SW_HIDE = 0x40, 0
ERREUR_ANNULEE = 1223  # ERROR_CANCELLED : autorisation refusée
EN_COURS = 0x102  # WAIT_TIMEOUT

# Exécuté en administrateur. $ids, $paquet et $etat sont ajoutés au début (voir script()).
SCRIPT_INSTALLATION = r"""
$resultat = @{ fini = $false; etape = ''; windows_update = $null; nvidia = $null }
function Ecrire { $resultat | ConvertTo-Json -Depth 4 -Compress | Set-Content -LiteralPath $etat -Encoding UTF8 }
if ($ids.Count -gt 0) {
  try {
    $resultat.etape = 'windows_update'; Ecrire
    $session = New-Object -ComObject Microsoft.Update.Session
    $session.ClientApplicationID = 'Bilan sante PC'
    $choisies = New-Object -ComObject Microsoft.Update.UpdateColl
    foreach ($maj in $session.CreateUpdateSearcher().Search("IsInstalled=0 and Type='Driver'").Updates) {
      if ($ids -contains $maj.Identity.UpdateID) {
        if (-not $maj.EulaAccepted) { $maj.AcceptEula() }
        [void]$choisies.Add($maj)
      }
    }
    $wu = @{ installees = 0; redemarrage = $false }
    if ($choisies.Count -gt 0) {
      $telechargement = $session.CreateUpdateDownloader(); $telechargement.Updates = $choisies
      [void]$telechargement.Download()
      $installation = $session.CreateUpdateInstaller(); $installation.Updates = $choisies
      $fin = $installation.Install()
      for ($i = 0; $i -lt $choisies.Count; $i++) {
        if ($fin.GetUpdateResult($i).ResultCode -in 2, 3) { $wu.installees++ }
      }
      $wu.redemarrage = [bool]$fin.RebootRequired
    }
    $resultat.windows_update = $wu
  } catch { $resultat.windows_update = @{ erreur = $_.Exception.Message } }
}
if ($paquet) {
  try {
    $resultat.etape = 'nvidia'; Ecrire
    # Copie dans un dossier de Windows, que seul un administrateur peut modifier, puis vérification de la signature.
    $dossier = Join-Path $env:windir ('Temp\BilanSantePC-' + [guid]::NewGuid())
    New-Item -ItemType Directory -Path $dossier | Out-Null
    $copie = Join-Path $dossier (Split-Path $paquet -Leaf)
    Copy-Item -LiteralPath $paquet -Destination $copie
    $signature = Get-AuthenticodeSignature -LiteralPath $copie
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=NVIDIA Corporation') {
      $resultat.nvidia = @{ erreur = 'Le fichier téléchargé n''est pas signé par NVIDIA' }
    } else {
      $processus = Start-Process -FilePath $copie -ArgumentList '-s', '-noreboot' -PassThru
      $processus.WaitForExit()
      $resultat.nvidia = @{ code = $processus.ExitCode }
    }
    Remove-Item -LiteralPath $dossier -Recurse -Force -ErrorAction SilentlyContinue
  } catch { $resultat.nvidia = @{ erreur = $_.Exception.Message } }
}
$resultat.fini = $true; $resultat.etape = ''; Ecrire
"""


class Annulee(Exception):
    """L'utilisateur a refusé l'autorisation administrateur."""


def dossier() -> Path:
    return dossier_par_defaut() / "pilotes"


def fichier_etat() -> Path:
    return dossier() / "etat.json"


# --- Téléchargement du pilote NVIDIA ---

def _ouvrir(url: str):
    return urllib.request.urlopen(urllib.request.Request(url, headers=pilotes.ENTETES), timeout=pilotes.DELAI)


def telecharger_nvidia(derniere: dict, progression: Callable[[float], None], arret: Callable[[], bool]) -> Path | None:
    """Télécharge le pilote NVIDIA `derniere` (voir pilotes.derniere_nvidia) ; None si `arret()` devient vrai.

    Déjà là en entier (une installation refusée puis relancée) : il n'est pas téléchargé une deuxième fois. Les autres
    fichiers du dossier (anciennes versions) sont effacés.
    """
    if not pilotes.ORIGINE_NVIDIA.match(derniere["url"]):
        raise ValueError(f"Adresse inattendue : {derniere['url']}")
    chemin = dossier() / derniere["url"].rsplit("/", 1)[1]
    dossier().mkdir(parents=True, exist_ok=True)
    for ancien in dossier().glob("*.exe"):
        if ancien != chemin:
            ancien.unlink(missing_ok=True)
    with _ouvrir(derniere["url"]) as reponse:
        taille = int(reponse.headers.get("Content-Length") or 0)
        if not 0 < taille <= TAILLE_MAX:
            raise ValueError(f"Taille inattendue : {taille} octets")
        if chemin.is_file() and chemin.stat().st_size == taille:
            progression(1.0)
            return chemin
        recus = 0
        with open(chemin, "wb") as sortie:
            while bloc := reponse.read(BLOC):
                if arret():
                    break
                recus += len(bloc)
                sortie.write(bloc)
                progression(min(recus / taille, 1.0))
    if arret() or recus != taille:
        chemin.unlink(missing_ok=True)
        if arret():
            return None
        raise ValueError(f"Téléchargement incomplet : {recus} octets sur {taille}")
    return chemin


# --- Installation, en administrateur ---

def _texte_powershell(texte: str) -> str:
    return "'" + texte.replace("'", "''") + "'"


def script(ids: list[str], paquet: Path | None, etat: Path) -> str:
    """Le script d'installation, avec ses paramètres : pilotes de Windows Update (identifiants vérifiés), pilote
    NVIDIA téléchargé, fichier où noter l'avancement."""
    if not all(ID_WINDOWS_UPDATE.match(identifiant) for identifiant in ids):
        raise ValueError(f"Identifiant de Windows Update invalide : {ids}")
    liste = ", ".join(_texte_powershell(identifiant) for identifiant in ids)
    return (f"$ids = @({liste})\n$paquet = {_texte_powershell(str(paquet) if paquet else '')}\n"
            f"$etat = {_texte_powershell(str(etat))}\n" + SCRIPT_INSTALLATION)


class _Execution(ctypes.Structure):  # SHELLEXECUTEINFOW
    _fields_ = [("taille", wintypes.DWORD), ("options", wintypes.ULONG), ("fenetre", wintypes.HWND),
                ("verbe", wintypes.LPCWSTR), ("fichier", wintypes.LPCWSTR), ("parametres", wintypes.LPCWSTR),
                ("dossier", wintypes.LPCWSTR), ("affichage", ctypes.c_int), ("instance", wintypes.HINSTANCE),
                ("liste", ctypes.c_void_p), ("classe", wintypes.LPCWSTR), ("cle_classe", wintypes.HKEY),
                ("raccourci", wintypes.DWORD), ("icone", wintypes.HANDLE), ("processus", wintypes.HANDLE)]


def _lancer_en_administrateur(fichier: str, parametres: str, fenetre: int | None) -> int:
    """Lance `fichier` en administrateur (Windows demande l'autorisation, devant `fenetre`, sinon la demande peut
    rester cachée dans la barre des tâches) ; renvoie le handle de son processus."""
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    execution = _Execution(taille=ctypes.sizeof(_Execution), options=SEE_MASK_NOCLOSEPROCESS, fenetre=fenetre,
                           verbe="runas", fichier=fichier, parametres=parametres, affichage=SW_HIDE)
    if not shell32.ShellExecuteExW(ctypes.byref(execution)):
        erreur = ctypes.get_last_error()
        if erreur == ERREUR_ANNULEE:
            raise Annulee()
        raise ctypes.WinError(erreur)
    return execution.processus


def lancer(ids: list[str], paquet: Path | None, fenetre: int | None = None) -> int:
    """Lance l'installation en administrateur ; renvoie le handle du processus (voir termine)."""
    dossier().mkdir(parents=True, exist_ok=True)
    fichier_etat().unlink(missing_ok=True)
    encode = base64.b64encode(script(ids, paquet, fichier_etat()).encode("utf-16-le")).decode("ascii")
    return _lancer_en_administrateur("powershell.exe", "-NoProfile -NonInteractive -ExecutionPolicy Bypass "
                                                       f"-WindowStyle Hidden -EncodedCommand {encode}", fenetre)


def termine(processus: int) -> bool:
    """Vrai quand l'installation est finie (le handle est alors fermé)."""
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    if kernel32.WaitForSingleObject(processus, 0) == EN_COURS:
        return False
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle(processus)
    return True


def lire_etat() -> dict:
    """Où en est l'installation (étape en cours, puis résultat) ; vide si rien n'est encore noté."""
    try:
        return json.loads(fichier_etat().read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


# --- Résultat ---

def bilan(etat: dict, mises_a_jour: list[dict], nvidia: dict | None) -> dict:
    """Ce qui a été installé, d'après l'état final et la version NVIDIA relue dans le registre.

    Renvoie : installes (noms), echecs (phrases), redemarrage (bool).
    """
    installes, echecs, redemarrage = [], [], False
    if mises_a_jour:
        windows = etat.get("windows_update") or {"erreur": "aucun résultat"}
        if windows.get("erreur"):
            journal.error("Pilotes de Windows Update non installés : %s", windows["erreur"])
            echecs.append("Les pilotes de Windows Update n'ont pas pu être installés.")
        else:
            nombre = int(windows.get("installees") or 0)
            if nombre:
                installes.append(f"{nombre} pilote{'s' if nombre > 1 else ''} de Windows Update")
            if (restants := len(mises_a_jour) - nombre) > 0:
                echecs.append(f"{restants} pilote{'s' if restants > 1 else ''} de Windows Update "
                              + ("n'ont pas pu être installés." if restants > 1 else "n'a pas pu être installé."))
            redemarrage = bool(windows.get("redemarrage"))
    if pilotes.nvidia_a_installer(nvidia):
        attendue = nvidia["derniere"]["version"]
        resultat = etat.get("nvidia") or {"erreur": "aucun résultat"}
        relue = version_nvidia_installee(nvidia["carte"])
        if relue == attendue:
            installes.append(f"pilote NVIDIA {attendue}")
        elif resultat.get("erreur") or resultat.get("code") not in (0, 1):
            journal.error("Pilote NVIDIA non installé : %s (version relue : %s)", resultat, relue)
            echecs.append("Le pilote NVIDIA n'a pas pu être installé.")
        else:  # installé, mais Windows ne l'utilisera qu'après un redémarrage
            installes.append(f"pilote NVIDIA {attendue}")
            redemarrage = True
    return {"installes": installes, "echecs": echecs, "redemarrage": redemarrage}


def version_nvidia_installee(carte: str) -> str | None:
    """Version NVIDIA du pilote de la carte `carte`, relue dans le registre."""
    for pilote in pilotes.pilotes_installes():
        if pilote["nom"] == carte:
            return pilotes.version_nvidia(pilote["version"])
    return None


def nettoyer() -> None:
    """Efface le pilote téléchargé et le fichier d'état, une fois l'installation finie."""
    shutil.rmtree(dossier(), ignore_errors=True)
