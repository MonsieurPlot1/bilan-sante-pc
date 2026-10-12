"""Journal local : fichier texte dans %LOCALAPPDATA%\\BilanSantePC. Rien n'est envoyé ailleurs."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import config


def dossier_par_defaut() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "BilanSantePC"


def configurer(dossier: Path | None = None) -> Path | None:
    """Écrit le journal dans `dossier`/bilan.log ; renvoie le chemin, ou None si impossible."""
    fichier = (dossier or dossier_par_defaut()) / "bilan.log"
    try:
        fichier.parent.mkdir(parents=True, exist_ok=True)
        # 3 fichiers de 1 Mo au plus : le journal ne grossit pas sans fin.
        gestionnaire = RotatingFileHandler(fichier, maxBytes=1024**2, backupCount=2, encoding="utf-8")
    except OSError:
        return None  # pas de journal plutôt qu'une application qui ne démarre pas
    gestionnaire.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s : %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[gestionnaire], force=True)
    # Les plantages non prévus finissent aussi dans le journal (le .exe n'a pas de console).
    sys.excepthook = lambda *erreur: logging.getLogger("plantage").critical("Erreur non gérée", exc_info=erreur)
    logging.getLogger(__name__).info("Bilan santé PC v%s démarré", config.VERSION)
    return fichier
