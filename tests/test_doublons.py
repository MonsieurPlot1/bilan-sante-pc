"""Tests du module doublons. Lancer avec : python -m pytest"""

import os
import subprocess
from collections import namedtuple
from pathlib import Path

import pytest

from modules import doublons, stockage

Usage = namedtuple("Usage", "total used free percent")


def ecrire(racine: Path, chemin: str, contenu: bytes) -> Path:
    cible = racine / chemin
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(contenu)
    return cible


@pytest.fixture
def releve(tmp_path, monkeypatch):
    """Relève les fichiers personnels d'un faux disque, comme le fait l'analyse du stockage."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "profil-absent"))
    monkeypatch.setenv("SystemRoot", str(tmp_path / "disque" / "Windows"))
    monkeypatch.setattr(stockage.psutil, "disk_usage", lambda _: Usage(10**9, 10**8, 9 * 10**8, 10.0))
    monkeypatch.setattr(stockage, "corbeille", lambda _: 0)
    # Petits seuils : les fichiers des tests restent minuscules.
    monkeypatch.setattr(doublons, "TAILLE_MIN_FICHIER", 1000)
    monkeypatch.setattr(doublons, "TAILLE_MIN_DOSSIER", 5000)
    monkeypatch.setattr(doublons, "ECHANTILLON", 64)
    monkeypatch.setattr(doublons, "BLOC", 256)
    return lambda: stockage.scan(str(tmp_path / "disque"))["personnels"]


@pytest.fixture
def disque(tmp_path) -> Path:
    racine = tmp_path / "disque"
    film, autre, photo1, photo2 = (os.urandom(n) for n in (4000, 4000, 3000, 3000))
    photo3 = os.urandom(1000)
    piege = film[:64] + os.urandom(4000 - 128) + film[-64:]  # même début et même fin que le film, pas le milieu
    for chemin, contenu in {
        "Downloads/film.rar": film, "Downloads/film (1).rar": film, "Bureau/copie.rar": film,
        "Downloads/autre.rar": autre, "Downloads/piege.rar": piege,
        "Petits/a.txt": b"x" * 500, "Petits/b.txt": b"x" * 500,  # en double, mais trop petits pour compter
        "Photos/Vacances/p1.jpg": photo1, "Photos/Vacances/p2.jpg": photo2,
        "Photos/Vacances/Jour1/p3.jpg": photo3, "Photos/Vacances/mini.txt": b"m" * 10,
        "Photos/note.txt": b"n" * 10,  # Photos n'est donc pas une copie de Sauvegarde : Vacances, si
        "Sauvegarde/Vacances/p1.jpg": photo1, "Sauvegarde/Vacances/p2.jpg": photo2,
        "Sauvegarde/Vacances/Jour1/p3.jpg": photo3, "Sauvegarde/Vacances/mini.txt": b"m" * 10,
        "Ailleurs/p1.jpg": photo1,
        # Même forme que Vacances, mais p2 change au milieu : pas une copie du dossier.
        "Presque/Vacances/p1.jpg": photo1, "Presque/Vacances/p2.jpg": photo2[:64] + os.urandom(3000 - 128)
        + photo2[-64:], "Presque/Vacances/Jour1/p3.jpg": photo3, "Presque/Vacances/mini.txt": b"m" * 10,
    }.items():
        ecrire(racine, chemin, contenu)
    return racine


def resume(resultat: dict, racine: Path) -> list[tuple]:
    return [(g["dossier"], sorted(os.path.relpath(c, racine) for c in g["copies"]), g["en_trop"])
            for g in resultat["groupes"]]


def test_doublons(releve, disque):
    etapes = {}
    resultat = doublons.chercher(releve(), lambda etape, fait, total: etapes.update({etape: (fait, total)}))
    assert resume(resultat, disque) == [
        (False, ["Bureau\\copie.rar", "Downloads\\film (1).rar", "Downloads\\film.rar"], 8000),
        (True, ["Photos\\Vacances", "Sauvegarde\\Vacances"], 7010),  # le dossier du haut, pas Jour1
        # Les copies dans les dossiers en double sont comptées avec eux : seules celles d'ailleurs sont en trop.
        (False, ["Ailleurs\\p1.jpg", "Photos\\Vacances\\p1.jpg", "Presque\\Vacances\\p1.jpg",
                 "Sauvegarde\\Vacances\\p1.jpg"], 6000),
        (False, ["Photos\\Vacances\\Jour1\\p3.jpg", "Presque\\Vacances\\Jour1\\p3.jpg",
                 "Sauvegarde\\Vacances\\Jour1\\p3.jpg"], 1000),
    ]
    assert resultat["nombre"] == 4 and resultat["en_trop"] == 22010
    assert etapes["rapide"][0] == etapes["rapide"][1] and etapes["contenu"][0] == etapes["contenu"][1] > 0


def test_retirer(releve, disque):
    """Après la mise à la Corbeille d'une copie ou d'un dossier, les groupes et la place en trop suivent."""
    trouves = doublons.chercher(releve())
    doublons.retirer(trouves, str(disque / "Ailleurs" / "p1.jpg"))
    doublons.retirer(trouves, str(disque / "Bureau" / "copie.rar"))
    assert resume(trouves, disque) == [
        (True, ["Photos\\Vacances", "Sauvegarde\\Vacances"], 7010),
        (False, ["Downloads\\film (1).rar", "Downloads\\film.rar"], 4000),
        (False, ["Photos\\Vacances\\p1.jpg", "Presque\\Vacances\\p1.jpg", "Sauvegarde\\Vacances\\p1.jpg"], 3000),
        (False, ["Photos\\Vacances\\Jour1\\p3.jpg", "Presque\\Vacances\\Jour1\\p3.jpg",
                 "Sauvegarde\\Vacances\\Jour1\\p3.jpg"], 1000),
    ]
    assert trouves["nombre"] == 4 and trouves["en_trop"] == 15010
    # Un des deux dossiers identiques : plus de dossier en double, ses fichiers ne comptent plus.
    doublons.retirer(trouves, str(disque / "Sauvegarde" / "Vacances"))
    # Un des deux derniers films : il n'est plus en double.
    doublons.retirer(trouves, str(disque / "Downloads" / "film.rar"))
    assert resume(trouves, disque) == [
        (False, ["Photos\\Vacances\\p1.jpg", "Presque\\Vacances\\p1.jpg"], 3000),
        (False, ["Photos\\Vacances\\Jour1\\p3.jpg", "Presque\\Vacances\\Jour1\\p3.jpg"], 1000),
    ]
    assert trouves["nombre"] == 2 and trouves["en_trop"] == 4000


def test_fichier_change_dans_un_dossier_en_double(releve, disque):
    """Un fichier enlevé d'un des dossiers identiques : ce dossier n'est plus une copie de l'autre."""
    trouves = doublons.chercher(releve())
    doublons.retirer(trouves, str(disque / "Photos" / "Vacances" / "p2.jpg"))
    assert not any(groupe["dossier"] for groupe in trouves["groupes"])


def test_lien_physique(releve, tmp_path):
    """Deux noms pour le même fichier : il n'y a rien en trop sur le disque."""
    original = ecrire(tmp_path / "disque", "Docs/rapport.pdf", os.urandom(2000))
    os.link(original, tmp_path / "disque" / "Docs" / "rapport-lien.pdf")
    assert doublons.chercher(releve())["groupes"] == []


def test_dossier_incomplet(releve, tmp_path):
    """Un dossier dont une partie n'a pas été lue (ici une jonction) n'est pas comparé en entier."""
    racine = tmp_path / "disque"
    for dossier in ("A/Album", "B/Album"):
        for nom in ("1.jpg", "2.jpg"):
            ecrire(racine, f"{dossier}/{nom}", nom.encode() * 3000)
    subprocess.run(["cmd", "/c", "mklink", "/J", str(racine / "B" / "Album" / "lien"), str(racine / "A")],
                   check=True, capture_output=True)
    groupes = doublons.chercher(releve())["groupes"]
    assert not any(g["dossier"] for g in groupes)
    assert len(groupes) == 2  # les fichiers, eux, restent comparés un par un


def test_bibliotheques_pas_montrees_seules(releve, tmp_path):
    contenu = os.urandom(2000)
    for chemin in ("Jeu1/moteur.dll", "Jeu2/moteur.dll"):
        ecrire(tmp_path / "disque", chemin, contenu)
    assert doublons.chercher(releve())["groupes"] == []


def test_arret(releve, disque):
    assert doublons.chercher(releve(), arret=lambda: True) is None


def test_fichier_illisible(releve, disque, monkeypatch):
    """Un fichier qui ne s'ouvre pas (utilisé par un autre programme…) n'est simplement pas comparé."""
    ouvrir = open

    def refuse(chemin, *arguments, **options):
        if str(chemin).endswith("copie.rar"):
            raise PermissionError("utilisé ailleurs")
        return ouvrir(chemin, *arguments, **options)
    monkeypatch.setattr("builtins.open", refuse)
    film = next(g for g in doublons.chercher(releve())["groupes"] if g["nom"].startswith("film"))
    assert len(film["copies"]) == 2


def test_empreinte_rapide(tmp_path, monkeypatch):
    monkeypatch.setattr(doublons, "ECHANTILLON", 4)
    a = ecrire(tmp_path, "a", b"debut-MILIEU1-fin")
    b = ecrire(tmp_path, "b", b"debut-MILIEU2-fin")
    assert doublons.empreinte_rapide(str(a), 17) == doublons.empreinte_rapide(str(b), 17)
    assert doublons.empreinte_complete(str(a), lambda _: None, lambda: False) != \
        doublons.empreinte_complete(str(b), lambda _: None, lambda: False)
