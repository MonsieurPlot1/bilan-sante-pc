"""Module batterie : niveau de charge, branchement et usure de la batterie.

Lecture seule : on interroge le pilote de batterie de Windows (IOCTL_BATTERY_QUERY_INFORMATION,
API publique et documentée), en ouvrant le périphérique en lecture uniquement.
"""

import ctypes
import uuid
from ctypes import wintypes

import psutil

GUID_BATTERIE = "72631e54-78a4-11d0-bcf7-00aa00b7b32a"  # GUID_DEVCLASS_BATTERY
DIGCF_PRESENT_INTERFACE = 0x12
GENERIC_READ = 0x80000000
OPEN_EXISTING = 3
IOCTL_TAG = 0x294040          # IOCTL_BATTERY_QUERY_TAG
IOCTL_INFORMATION = 0x294044  # IOCTL_BATTERY_QUERY_INFORMATION
BATTERIE_SYSTEME = 0x80000000   # BATTERY_SYSTEM_BATTERY : exclut les onduleurs
CAPACITE_RELATIVE = 0x40000000  # BATTERY_CAPACITY_RELATIVE : valeurs sans unité, inutilisables
CAPACITE_INCONNUE = 0xFFFFFFFF


class _Guid(ctypes.Structure):
    _fields_ = [("donnees", ctypes.c_ubyte * 16)]


class _Interface(ctypes.Structure):  # SP_DEVICE_INTERFACE_DATA
    _fields_ = [("cbSize", wintypes.DWORD), ("guid", _Guid), ("drapeaux", wintypes.DWORD),
                ("reserve", ctypes.c_void_p)]


class _Requete(ctypes.Structure):  # BATTERY_QUERY_INFORMATION
    _fields_ = [("tag", wintypes.ULONG), ("niveau", ctypes.c_int), ("parametre", wintypes.LONG)]


class _Information(ctypes.Structure):  # BATTERY_INFORMATION
    _fields_ = [("capacites", wintypes.ULONG), ("technologie", ctypes.c_ubyte), ("reserve", ctypes.c_ubyte * 3),
                ("chimie", ctypes.c_ubyte * 4), ("origine", wintypes.ULONG), ("actuelle", wintypes.ULONG),
                ("alerte1", wintypes.ULONG), ("alerte2", wintypes.ULONG), ("critique", wintypes.ULONG),
                ("cycles", wintypes.ULONG)]


def _api() -> tuple[ctypes.WinDLL, ctypes.WinDLL]:
    setupapi, kernel32 = ctypes.WinDLL("setupapi"), ctypes.WinDLL("kernel32")
    setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    setupapi.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                                     wintypes.DWORD, ctypes.c_void_p]
    setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                                          wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                     wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                         ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    return setupapi, kernel32


def _chemins_batteries(setupapi: ctypes.WinDLL) -> list[str]:
    """Chemins des périphériques batterie présents (souvent un seul)."""
    guid = _Guid.from_buffer_copy(uuid.UUID(GUID_BATTERIE).bytes_le)
    liste = setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, DIGCF_PRESENT_INTERFACE)
    if liste in (None, ctypes.c_void_p(-1).value):
        return []
    chemins = []
    try:
        index = 0
        while True:
            interface = _Interface(cbSize=ctypes.sizeof(_Interface))
            if not setupapi.SetupDiEnumDeviceInterfaces(liste, None, ctypes.byref(guid), index,
                                                        ctypes.byref(interface)):
                break
            index += 1
            taille = wintypes.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(liste, ctypes.byref(interface), None, 0,
                                                      ctypes.byref(taille), None)
            if taille.value < 8:
                continue
            tampon = ctypes.create_string_buffer(taille.value)
            # cbSize de SP_DEVICE_INTERFACE_DETAIL_DATA_W : 8 en 64 bits, 6 en 32 bits.
            ctypes.c_uint32.from_buffer(tampon).value = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if setupapi.SetupDiGetDeviceInterfaceDetailW(liste, ctypes.byref(interface), tampon, taille,
                                                         None, None):
                chemins.append(ctypes.wstring_at(ctypes.addressof(tampon) + 4))
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(liste)
    return chemins


def _information(kernel32: ctypes.WinDLL, chemin: str) -> _Information | None:
    """Lit BATTERY_INFORMATION d'une batterie, en lecture seule."""
    poignee = kernel32.CreateFileW(chemin, GENERIC_READ, 3, None, OPEN_EXISTING, 0, None)
    if poignee in (None, wintypes.HANDLE(-1).value):
        return None
    try:
        attente, tag, lus = wintypes.ULONG(0), wintypes.ULONG(), wintypes.DWORD()
        if not kernel32.DeviceIoControl(poignee, IOCTL_TAG, ctypes.byref(attente), 4, ctypes.byref(tag), 4,
                                        ctypes.byref(lus), None) or not tag.value:
            return None
        requete, information = _Requete(tag=tag.value, niveau=0), _Information()  # niveau 0 : BatteryInformation
        if not kernel32.DeviceIoControl(poignee, IOCTL_INFORMATION, ctypes.byref(requete), ctypes.sizeof(requete),
                                        ctypes.byref(information), ctypes.sizeof(information),
                                        ctypes.byref(lus), None):
            return None
        return information
    finally:
        kernel32.CloseHandle(poignee)


def capacites() -> tuple[int, int] | None:
    """(capacité d'origine, capacité actuelle) en mWh, toutes batteries cumulées, ou None."""
    try:
        setupapi, kernel32 = _api()
        infos = [_information(kernel32, chemin) for chemin in _chemins_batteries(setupapi)]
    except OSError:
        return None
    valides = [i for i in infos if i and i.capacites & BATTERIE_SYSTEME and not i.capacites & CAPACITE_RELATIVE
               and CAPACITE_INCONNUE not in (i.origine, i.actuelle)]
    if not valides:
        return None
    return sum(i.origine for i in valides), sum(i.actuelle for i in valides)


def sante(origine: int, actuelle: int) -> float | None:
    """Part de la capacité d'origine encore disponible (0 à 1), ou None si les chiffres sont incohérents."""
    if origine <= 0 or actuelle <= 0 or actuelle > origine * 1.5:
        return None
    return min(1.0, actuelle / origine)  # une batterie neuve dépasse parfois un peu sa capacité nominale


def scan() -> dict:
    """Point d'entrée du module. Sans batterie (PC fixe), le module est « non applicable »."""
    batterie = psutil.sensors_battery()
    if batterie is None:
        return {"applicable": False, "score": None, "constats": []}

    branchement = {True: "branchée sur le secteur", False: "sur batterie"}.get(batterie.power_plugged,
                                                                            "branchement inconnu")
    constats = [f"Batterie chargée à {batterie.percent:.0f} %, {branchement}."]
    capacite = capacites()
    part = sante(*capacite) if capacite else None
    if part is None:
        constats.append("Usure non mesurable sur ce PC.")
    else:
        constats.append(f"La batterie garde {part * 100:.0f} % de sa capacité d'origine "
                        f"(usure : {(1 - part) * 100:.0f} %).")
    return {
        "applicable": True,
        "score": None,  # calculé ensuite par modules/score.calculer()
        "constats": constats,
        "niveau": batterie.percent,
        "branche": batterie.power_plugged,
        "sante": part,
        "capacites": capacite,
    }
