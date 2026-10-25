"""Tests du module stockage. Lancer avec : python -m pytest"""

import ctypes
import os
import shutil
import subprocess
from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace

import pytest

from modules import stockage

Usage = namedtuple("Usage", "total used free percent")
UTILISE = 10_000  # octets utilisés sur le faux disque


def fichier(racine: Path, chemin: str, taille: int) -> None:
    cible = racine / chemin
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(b"x" * taille)


@pytest.fixture
def disque(tmp_path, monkeypatch) -> Path:
    """Faux disque : un profil, des logiciels, un jeu Steam, des caches, Windows et Windows.old."""
    racine = tmp_path / "disque"
    profil = racine / "Users" / "moi"
    monkeypatch.setenv("USERPROFILE", str(profil))
    monkeypatch.setenv("LOCALAPPDATA", str(profil / "AppData" / "Local"))
    monkeypatch.setenv("SystemRoot", str(racine / "Windows"))
    monkeypatch.setattr(stockage.tempfile, "gettempdir", lambda: str(profil / "AppData" / "Local" / "Temp"))
    monkeypatch.setattr(stockage.psutil, "disk_usage", lambda _: Usage(20_000, UTILISE, 10_000, 50.0))
    monkeypatch.setattr(stockage, "corbeille", lambda _: 25)
    for chemin, taille in {
        "Program Files/Editeur/app.exe": 100,
        "Program Files (x86)/Steam/steamapps/common/Jeu/data.pak": 500,
        "Program Files (x86)/Steam/steamapps/common/Jeu/intro.mp4": 50,  # vidéo d'un jeu : Jeux
        "Users/moi/Videos/film.mkv": 300,
        "Users/moi/Downloads/setup.exe": 200,
        "Users/moi/Downloads/notes.pdf": 10,
        "Users/moi/divers.xyz": 3,
        "Users/moi/.ollama/modele": 30,
        "Users/moi/AppData/Local/Discord/app.dll": 60,
        "Users/moi/AppData/Local/Discord/Cache/donnees": 40,
        "Users/moi/AppData/Local/Temp/f.tmp": 5,
        "Windows/System32/noyau.dll": 999,  # pas parcouru : compté dans Système par différence
        "Windows/Temp/journal": 7,
        "Windows.old/Program Files (x86)/Steam/ancien": 70,  # copie de l'ancien Windows : Sauvegardes
        "pagefile.sys": 1000,
    }.items():
        fichier(racine, chemin, taille)
    return racine


def categories(resultat: dict) -> dict[str, dict]:
    return {c["cle"]: c for c in resultat["categories"]}


def test_classement(disque):
    resultat = stockage.scan(str(disque))
    tailles = {cle: c["taille"] for cle, c in categories(resultat).items()}
    assert tailles == {"applications": 100 + 30 + 60, "jeux": 550, "videos": 300, "photos": 0, "musique": 0,
                       "documents": 10, "archives": 200, "temporaires": 40 + 5 + 7, "corbeille": 25,
                       "sauvegardes": 70, "autres": 3, "systeme": UTILISE - 1400}
    assert sum(tailles.values()) == UTILISE  # tout l'espace utilisé est expliqué
    assert resultat["fichiers"] == 13  # Windows\System32 n'est pas parcouru, pagefile.sys est à part


def test_elements(disque):
    parties = categories(stockage.scan(str(disque)))
    jeux = parties["jeux"]["elements"]
    assert [(e["nom"], e["taille"], e["dossier"]) for e in jeux] == [("Jeu", 550, True)]
    applications = [(e["nom"], e["taille"]) for e in parties["applications"]["elements"]]
    assert applications == [("Editeur", 100), ("Discord", 60), (".ollama", 30)]
    temporaires = [e["nom"] for e in parties["temporaires"]["elements"]]
    assert temporaires == ["Discord › Cache", "Windows › Temp", "Fichiers temporaires de Windows"]
    archives = parties["archives"]
    assert archives["elements"][0] | {"chemin": "?"} == {"nom": "setup.exe", "chemin": "?", "taille": 200,
                                                        "dossier": False}
    assert [(d["nom"], d["taille"]) for d in archives["surtout_dans"]] == [("Téléchargements", 200)]
    systeme = [(e["nom"], e["taille"]) for e in parties["systeme"]["elements"]]
    assert systeme == [("Windows et fichiers protégés", UTILISE - 1400 - 1000),
                       ("Mémoire virtuelle (pagefile.sys)", 1000)]
    assert parties["corbeille"]["elements"][0]["chemin"] is None  # rien à ouvrir dans l'Explorateur
    assert parties["temporaires"]["surtout_dans"] == []  # classés par emplacement : pas de « surtout dans »


def test_jonction_non_comptee(disque):
    """Une jonction pointe vers un dossier déjà compté : la suivre le compterait deux fois."""
    lien = disque / "Users" / "moi" / "raccourci"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(lien), str(disque / "Users" / "moi" / "Videos")],
                   check=True, capture_output=True)
    assert categories(stockage.scan(str(disque)))["videos"]["taille"] == 300


def test_progression_et_arret(disque, monkeypatch):
    monkeypatch.setattr(stockage, "INTERVALLE_PROGRESSION", 0)
    appels = []
    stockage.scan(str(disque), lambda octets, nombre: appels.append((octets, nombre)))
    assert appels and appels[-1][1] == 13
    assert all(a <= b for a, b in zip(appels, appels[1:]))  # ça ne fait qu'avancer
    assert stockage.scan(str(disque), arret=lambda: True) is None


def test_espace_utilise_plus_petit_que_les_fichiers(disque, monkeypatch):
    """Système garde au moins les fichiers de Windows mesurés, même si les fichiers comptés dépassent
    l'espace annoncé (copies comptées en double)."""
    monkeypatch.setattr(stockage.psutil, "disk_usage", lambda _: Usage(20_000, 500, 19_500, 2.5))
    systeme = categories(stockage.scan(str(disque)))["systeme"]
    assert systeme["taille"] == 1000
    assert [(e["nom"], e["taille"]) for e in systeme["elements"]] == [("Mémoire virtuelle (pagefile.sys)", 1000)]


def test_taille_sur_disque():
    assert stockage.taille_sur_disque("x", SimpleNamespace(st_file_attributes=0x20, st_size=42)) == 42
    en_ligne = SimpleNamespace(st_file_attributes=0x400000 | 0x20, st_size=10**9)  # OneDrive « en ligne »
    assert stockage.taille_sur_disque("x", en_ligne) == 0


def test_taille_compressee(tmp_path):
    chemin = tmp_path / "creux.bin"
    chemin.write_bytes(b"\0" * 4096)
    infos = SimpleNamespace(st_file_attributes=0x200, st_size=4096)  # marqué « creux » (sparse)
    assert stockage.taille_sur_disque(str(chemin), infos) == 4096  # Windows donne la place réelle


@pytest.mark.parametrize("chemin, attendu", [
    (r"C:\Users\moi\AppData\Local\Google\Chrome\User Data\Default\Cache", "Chrome › Cache"),
    (r"C:\Users\moi\AppData\Local\Packages\Microsoft.MinecraftUWP_8wekyb3d8bbwe", "Microsoft.MinecraftUWP"),
    (r"C:\Users\moi\AppData\Roaming\Apple Computer\MobileSync\Backup\00008110-001", "Sauvegarde d'iPhone ou d'iPad"),
    (r"C:\Program Files\Adobe", "Adobe"),
])
def test_nom_element(chemin, attendu):
    assert stockage.nom_element(chemin) == attendu


def test_dossier_du_profil_en_francais(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert stockage.nom_element(str(tmp_path / "Downloads")) == "Téléchargements"
    assert stockage.nom_element(str(tmp_path / "Projets" / "Downloads")) == "Downloads"  # pas le dossier du profil


def test_scan_reel_rapide(monkeypatch):
    """Sur le vrai PC, arrêté tout de suite : le module se lance sans erreur et n'invente rien."""
    assert stockage.scan(arret=lambda: True) is None
    assert stockage.disque_systeme().endswith(os.sep)


def test_fichiers_personnels(disque):
    """Ce que la recherche de doublons pourra comparer : les fichiers classés par extension, et leurs dossiers."""
    personnels = stockage.scan(str(disque))["personnels"]
    profil = str(disque / "Users" / "moi")
    videos = os.path.join(profil, "Videos")
    assert personnels["fichiers"][videos] == [("film.mkv", 300)]
    assert personnels["parents"][videos] == profil
    assert profil in personnels["incomplets"]  # il contient AppData, qui n'est pas personnel
    assert videos not in personnels["incomplets"]
    assert not any(dossier.startswith(os.path.join(profil, "AppData")) for dossier in personnels["fichiers"])


def test_supprimable(disque, monkeypatch):
    """« Supprimer » sur tout ce que l'analyse montre, sauf ce qui casserait Windows ou le profil."""
    profil = disque / "Users" / "moi"
    local = profil / "AppData" / "Local"
    monkeypatch.setenv("ProgramFiles", str(disque / "Program Files"))
    monkeypatch.setenv("ProgramData", str(disque / "ProgramData"))
    monkeypatch.setenv("APPDATA", str(profil / "AppData" / "Roaming"))
    monkeypatch.setenv("OneDrive", str(profil / "OneDrive"))
    for chemin in (profil / "Videos" / "film.mkv", profil / "Videos" / "Vacances", profil / ".ollama",
                   disque / "Program Files" / "Editeur", disque / "Program Files (x86)" / "Steam" / "steamapps",
                   local / "Discord", local / "Discord" / "Cache", disque / "Donnees" / "film.mkv"):
        assert stockage.supprimable(str(chemin)), chemin
    for chemin in (disque, disque / "Windows" / "Temp", disque / "Windows.old", local / "Temp", local / "Microsoft",
                   disque / "Program Files", disque / "Program Files" / "WindowsApps",
                   disque / "ProgramData" / "Microsoft", disque / "ProgramData" / "Package Cache",
                   local / "Packages" / "Microsoft.Photos_8wekyb3d8bbwe", local, profil / "AppData",
                   profil / "Videos", profil / "Downloads", profil / "OneDrive", profil, disque / "Users"):
        assert not stockage.supprimable(str(chemin)), chemin
    assert not stockage.supprimable(None) and not stockage.supprimable("C:\\")


def test_contenu(tmp_path):
    """Ce qui part avec un dossier personnel, classé comme pendant l'analyse (confirmation et chiffres)."""
    dossier = tmp_path / "Vacances"
    for chemin, taille in {"film.mp4": 300, "Jour1/photo.jpg": 20, "Jour1/notes.txt": 5, "inconnu.xyz": 2,
                           "desktop.ini": 7}.items():
        fichier(dossier, chemin, taille)
    ctypes.windll.kernel32.SetFileAttributesW(str(dossier / "desktop.ini"), 0x4)  # SYSTEM : reste dans Système
    assert stockage.contenu(str(dossier)) == ({"videos": 300, "photos": 20, "documents": 5, "autres": 2}, 4)
    assert stockage.contenu(str(dossier / "film.mp4"), "videos") == ({"videos": 300}, 1)
    with pytest.raises(OSError):
        stockage.contenu(str(dossier / "absent"))


def test_contenu_d_un_logiciel(disque):
    """Un dossier rangé par son emplacement : ce qu'il contient compte comme pendant l'analyse (son cache à part)."""
    discord = disque / "Users" / "moi" / "AppData" / "Local" / "Discord"
    assert stockage.contenu(str(discord), "applications") == ({"applications": 60, "temporaires": 40}, 2)
    jeu = disque / "Program Files (x86)" / "Steam" / "steamapps" / "common" / "Jeu"
    assert stockage.contenu(str(jeu), "jeux") == ({"jeux": 550}, 2)  # sa vidéo aussi


def test_retirer(disque, monkeypatch):
    """Un fichier supprimé : sa catégorie diminue, la place est libérée, Système ne bouge pas."""
    resultat = stockage.scan(str(disque))
    film = disque / "Users" / "moi" / "Videos" / "film.mkv"
    film.unlink()
    monkeypatch.setattr(stockage.psutil, "disk_usage", lambda _: Usage(20_000, UTILISE - 300, 10_300, 48.5))
    stockage.retirer(resultat, str(film), False, {"videos": 300})
    parties = categories(resultat)
    assert parties["videos"]["taille"] == 0 and parties["videos"]["elements"] == []
    assert parties["videos"]["surtout_dans"] == []
    assert parties["corbeille"]["taille"] == 25
    assert parties["systeme"]["taille"] == UTILISE - 1400
    assert sum(c["taille"] for c in resultat["categories"]) == resultat["utilise"] == UTILISE - 300


def test_retirer_un_dossier(disque, monkeypatch):
    for chemin, taille in {"Users/moi/Projet/clip.mp4": 100, "Users/moi/Projet/Notes/plan.pdf": 10}.items():
        fichier(disque, chemin, taille)
    resultat = stockage.scan(str(disque))
    systeme = categories(resultat)["systeme"]["taille"]
    projet = disque / "Users" / "moi" / "Projet"
    shutil.rmtree(projet)
    monkeypatch.setattr(stockage.psutil, "disk_usage", lambda _: Usage(20_000, UTILISE - 110, 10_110, 49.5))
    stockage.retirer(resultat, str(projet), True, {"videos": 100, "documents": 10})
    parties = categories(resultat)
    assert (parties["videos"]["taille"], parties["documents"]["taille"],
            parties["corbeille"]["taille"]) == (300, 10, 25)
    assert parties["systeme"]["taille"] == systeme  # Système ne bouge pas
    assert (resultat["utilise"], resultat["libre"]) == (UTILISE - 110, 10_110)
    assert [e["nom"] for e in parties["videos"]["elements"]] == ["film.mkv"]
    assert [d["nom"] for d in parties["videos"]["surtout_dans"]] == ["Vidéos"]


def test_fichier_systeme_dans_systeme(disque):
    """Un fichier de Windows dans le profil (registre, desktop.ini…) n'est pas un fichier personnel."""
    registre = disque / "Users" / "moi" / "NTUSER.DAT"
    registre.write_bytes(b"r" * 77)
    ctypes.windll.kernel32.SetFileAttributesW(str(registre), 0x4)  # SYSTEM
    resultat = stockage.scan(str(disque))
    assert categories(resultat)["autres"]["taille"] == 3  # comme avant : il reste dans Système
    assert ("NTUSER.DAT", 77) not in resultat["personnels"]["fichiers"][str(disque / "Users" / "moi")]
