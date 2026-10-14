"""Module alimentation : le PC est-il bridé par un mode d'économie d'énergie ?

Lecture seule : on demande à Windows le mode d'alimentation en vigueur, on ne change aucun réglage.
"""

import ctypes
import threading
import uuid
from ctypes import wintypes

# Mode d'alimentation en vigueur (EFFECTIVE_POWER_MODE de powrprof.h), en français.
MODES = {0: "économiseur d'énergie", 1: "meilleure efficacité énergétique", 2: "équilibré",
         3: "performances élevées", 4: "performances maximales", 5: "mode jeu", 6: "réalité mixte"}
ECONOMISEUR, EFFICACITE = 0, 1
PLAN_ECONOMIES = uuid.UUID("a1841308-3541-4fab-bc81-f71556f20b4a")  # mode de gestion « Économies d'énergie »
EFFECTIVE_POWER_MODE_V2 = 2

_Rappel = ctypes.WINFUNCTYPE(None, ctypes.c_int, ctypes.c_void_p)


def mode_effectif() -> int | None:
    """Mode d'alimentation en vigueur (clé de MODES), ou None si Windows ne répond pas.

    Windows envoie le mode à un rappel, depuis un autre thread, juste après l'inscription.
    """
    powrprof = ctypes.WinDLL("powrprof")
    powrprof.PowerRegisterForEffectivePowerModeNotifications.restype = ctypes.c_long
    powrprof.PowerRegisterForEffectivePowerModeNotifications.argtypes = [
        wintypes.ULONG, _Rappel, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    powrprof.PowerUnregisterFromEffectivePowerModeNotifications.argtypes = [ctypes.c_void_p]
    recus, arrive = [], threading.Event()

    @_Rappel
    def rappel(mode: int, _contexte) -> None:
        recus.append(mode)
        arrive.set()

    inscription = ctypes.c_void_p()
    if powrprof.PowerRegisterForEffectivePowerModeNotifications(EFFECTIVE_POWER_MODE_V2, rappel, None,
                                                                 ctypes.byref(inscription)):
        return None
    try:
        arrive.wait(1)
    finally:
        powrprof.PowerUnregisterFromEffectivePowerModeNotifications(inscription)
    return recus[-1] if recus else None


def plan_economies() -> bool:
    """Vrai si le mode de gestion de l'alimentation « Économies d'énergie » est choisi."""
    powrprof, kernel32 = ctypes.WinDLL("powrprof"), ctypes.WinDLL("kernel32")
    powrprof.PowerGetActiveScheme.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    guid = ctypes.c_void_p()
    if powrprof.PowerGetActiveScheme(None, ctypes.byref(guid)):
        return False
    try:
        return uuid.UUID(bytes_le=ctypes.string_at(guid.value, 16)) == PLAN_ECONOMIES
    finally:
        kernel32.LocalFree(guid)  # mémoire allouée par Windows pour la réponse


def scan() -> dict:
    """Point d'entrée du module (hors score) : renvoie le mode et les constats."""
    mode, plan = mode_effectif(), plan_economies()
    constats = [f"Mode d'alimentation : {MODES.get(mode, 'inconnu')}." if mode is not None
                else "Mode d'alimentation non lisible sur ce PC."]
    if plan:
        constats.append("Mode de gestion de l'alimentation : Économies d'énergie.")
    return {
        "score": None,  # hors score : voir modules/score.conseil_alimentation()
        "constats": constats,
        "mode": mode,
        "plan_economies": plan,
    }
