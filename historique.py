"""Historique des analyses : un fichier JSON local dans %LOCALAPPDATA%\\BilanSantePC.

Seulement des chiffres (date, scores, espace utilisé) : aucun nom de programme ni de fichier.
Rien n'est envoyé ailleurs.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import config
from journal import dossier_par_defaut
from modules.disque import taille_lisible
from modules.score import disque_systeme

journal = logging.getLogger(__name__)

NB_MAX_ENTREES = 200  # le fichier ne grossit pas sans fin
NB_POINTS_GRAPHIQUE = 20
SEUIL_DISQUE = 500 * 1024**2  # en dessous, la différence d'espace disque n'est pas signalée
# Évolution du disque sur le dernier mois : au moins une semaine de recul, signalée à partir de 1 Go.
RECUL_MIN, RECUL_MAX = timedelta(days=7), timedelta(days=30)
SEUIL_TENDANCE = 1024**3


def fichier(dossier: Path | None = None) -> Path:
    return (dossier or dossier_par_defaut()) / "historique.json"


def charger(dossier: Path | None = None) -> list[dict]:
    """Entrées de l'historique, de la plus ancienne à la plus récente."""
    chemin = fichier(dossier)
    try:
        entrees = json.loads(chemin.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        # Fichier abîmé : on le met de côté plutôt que de l'écraser, et on repart de zéro.
        journal.exception("Historique illisible, mis de côté")
        try:
            os.replace(chemin, chemin.with_suffix(".abime.json"))
        except OSError:
            pass
        return []
    return entrees if isinstance(entrees, list) else []


def entree(resultat: dict) -> dict | None:
    """Chiffres à garder d'une analyse, ou None si elle est incomplète (rien de fiable à comparer)."""
    bilan = resultat["bilan"]
    if not bilan or bilan["score"] is None:
        return None
    disque = resultat["modules"].get("disque")
    systeme = disque_systeme(disque["disques"]) if disque else None
    return {"date": resultat["date"].isoformat(timespec="seconds"), "score_version": bilan["version"],
            "score": bilan["score"], "scores": bilan["scores"],
            "disque_utilise": systeme["utilise"] if systeme else None}


def enregistrer(resultat: dict, dossier: Path | None = None) -> list[dict]:
    """Ajoute l'analyse à l'historique et renvoie l'historique à jour."""
    entrees = charger(dossier)
    nouvelle = entree(resultat)
    if nouvelle is None:
        return entrees
    entrees = (entrees + [nouvelle])[-NB_MAX_ENTREES:]
    chemin = fichier(dossier)
    temporaire = chemin.with_suffix(".tmp")
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        temporaire.write_text(json.dumps(entrees, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporaire, chemin)  # remplacement d'un coup : jamais de fichier à moitié écrit
    except OSError:
        journal.exception("Impossible d'enregistrer l'historique")
    return entrees


def effacer(dossier: Path | None = None) -> None:
    fichier(dossier).unlink(missing_ok=True)


def serie(entrees: list[dict]) -> list[dict]:
    """Les derniers scores calculés avec la version actuelle du calcul, pour le graphique."""
    return [e for e in entrees if e.get("score_version") == config.SCORE_VERSION][-NB_POINTS_GRAPHIQUE:]


def ecart(valeur: int) -> str:
    return f"+{valeur}" if valeur > 0 else "=" if valeur == 0 else str(valeur)


def tendance_disque(entrees: list[dict]) -> str | None:
    """Évolution de l'espace utilisé sur le disque de Windows sur le dernier mois, ou None.

    Référence : la plus ancienne analyse du dernier mois qui a au moins une semaine (sinon, pas assez de recul).
    """
    derniere = entrees[-1] if entrees else {}
    if derniere.get("disque_utilise") is None:
        return None
    fin = datetime.fromisoformat(derniere["date"])
    reference = next((e for e in entrees if e.get("disque_utilise") is not None
                      and RECUL_MIN <= fin - datetime.fromisoformat(e["date"]) <= RECUL_MAX), None)
    if reference is None:
        return None
    difference = derniere["disque_utilise"] - reference["disque_utilise"]
    if abs(difference) < SEUIL_TENDANCE:
        return None
    sens = "de plus" if difference > 0 else "de moins"
    return (f"Depuis le {datetime.fromisoformat(reference['date']):%d/%m} : {taille_lisible(abs(difference))} "
            f"{sens} utilisés sur le disque de Windows")


def comparer(entrees: list[dict], noms: dict[str, str]) -> list[str]:
    """Lignes « Depuis la dernière fois » entre les deux dernières analyses, puis l'évolution du disque."""
    if len(entrees) < 2:
        return ["Première analyse enregistrée : la comparaison sera possible la prochaine fois."]
    avant, apres = entrees[-2], entrees[-1]
    tendance = tendance_disque(entrees)
    if avant.get("score_version") != apres.get("score_version"):
        # L'espace disque ne dépend pas du calcul du score : son évolution reste valable.
        return ["Nouvelle version du calcul, pas de comparaison possible."] + ([tendance] if tendance else [])
    lignes = [f"Score : {apres['score']} ({ecart(apres['score'] - avant['score'])})"]
    for cle, nom in noms.items():
        if cle in apres["scores"] and cle in avant["scores"]:
            lignes.append(f"{nom} : {apres['scores'][cle]} ({ecart(apres['scores'][cle] - avant['scores'][cle])})")
    if avant.get("disque_utilise") is not None and apres.get("disque_utilise") is not None:
        difference = apres["disque_utilise"] - avant["disque_utilise"]
        if abs(difference) >= SEUIL_DISQUE:
            sens = "de plus" if difference > 0 else "de moins"
            lignes.append(f"Disque : {taille_lisible(abs(difference))} {sens} utilisés")
    date = datetime.fromisoformat(avant["date"])
    lignes.append(f"(comparé à l'analyse du {date:%d/%m/%Y à %H:%M})")
    return lignes + ([tendance] if tendance else [])
