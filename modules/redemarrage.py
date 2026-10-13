"""Module redémarrage : depuis quand Windows tourne sans vrai redémarrage, et redémarrage en attente.

Lecture seule : on lit l'heure de démarrage et deux clés du registre, on ne modifie rien.
"""

import time
import winreg

import psutil

# Clés créées par Windows quand une mise à jour attend un redémarrage pour s'installer.
CLES_EN_ATTENTE = [
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
]


def cle_existe(chemin: str) -> bool:
    """Vrai si la clé existe dans HKLM (vue 64 bits), ouverte en lecture seule."""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, chemin, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
            return True
    except OSError:  # clé absente ou accès refusé
        return False


def duree_lisible(jours: float) -> str:
    """« moins d'un jour », « 1 jour », « 12 jours »."""
    entiers = int(jours)
    return "moins d'un jour" if entiers < 1 else "1 jour" if entiers == 1 else f"{entiers} jours"


def scan() -> dict:
    """Point d'entrée du module : renvoie les mesures et les constats.

    Avec le démarrage rapide de Windows, « Arrêter » ne remet pas ce compteur à zéro :
    seul « Redémarrer » le fait. C'est voulu, c'est ce qui compte pour la fluidité.
    """
    jours = max(0.0, (time.time() - psutil.boot_time()) / 86400)
    en_attente = any(cle_existe(cle) for cle in CLES_EN_ATTENTE)
    constats = [f"Dernier redémarrage complet : il y a {duree_lisible(jours)}."]
    if en_attente:
        constats.append("Une mise à jour de Windows attend un redémarrage pour s'installer.")
    return {
        "score": None,  # calculé ensuite par modules/score.calculer()
        "constats": constats,
        "jours": jours,
        "en_attente": en_attente,
    }
