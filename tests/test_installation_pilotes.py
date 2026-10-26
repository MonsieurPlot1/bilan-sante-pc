"""Tests de l'installation des pilotes, sans réseau, sans PowerShell et sans rien installer (voir tests/conftest.py).
Lancer avec : python -m pytest"""

import base64
import io
import os

import pytest

from modules import installation_pilotes
from tests.test_pilotes import URL, nvidia_verifie

ID_GARMIN = "2fba6339-e495-4335-8575-5e211ed4522b"
GARMIN = [{"id": ID_GARMIN, "nom": "Garmin USB GPS"}]


@pytest.fixture(autouse=True)
def dossier_de_test(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))


class Reponse(io.BytesIO):
    """Réponse HTTP : son contenu et la taille annoncée."""

    def __init__(self, contenu: bytes, taille: int | None = None) -> None:
        super().__init__(contenu)
        self.headers = {"Content-Length": str(len(contenu) if taille is None else taille)}


def servir(contenu: bytes, taille: int | None = None):
    return lambda _url: Reponse(contenu, taille)


def derniere(url: str = URL) -> dict:
    return nvidia_verifie()["derniere"] | {"url": url}


def test_telecharger_nvidia(monkeypatch):
    donnees = os.urandom(3 * 1024**2 + 5)
    monkeypatch.setattr(installation_pilotes, "_ouvrir", servir(donnees))
    (installation_pilotes.dossier()).mkdir(parents=True)
    ancien = installation_pilotes.dossier() / "560.94-ancien.exe"
    ancien.write_bytes(b"vieux")
    parts = []
    chemin = installation_pilotes.telecharger_nvidia(derniere(), parts.append, lambda: False)
    assert chemin.name == "621.01-notebook-win10-win11-64bit-international-dch-whql.exe"
    assert chemin.read_bytes() == donnees and parts[-1] == 1.0 and parts == sorted(parts)
    assert not ancien.exists()  # une ancienne version téléchargée ne reste pas


def test_telecharger_nvidia_deja_la(monkeypatch):
    """Installation refusée puis relancée : le fichier complet n'est pas téléchargé une deuxième fois."""
    donnees = os.urandom(1000)
    monkeypatch.setattr(installation_pilotes, "_ouvrir", servir(b"", taille=len(donnees)))
    chemin = installation_pilotes.dossier() / URL.rsplit("/", 1)[1]
    chemin.parent.mkdir(parents=True)
    chemin.write_bytes(donnees)
    assert installation_pilotes.telecharger_nvidia(derniere(), lambda _part: None, lambda: False) == chemin
    assert chemin.read_bytes() == donnees


def test_telecharger_nvidia_arrete(monkeypatch):
    monkeypatch.setattr(installation_pilotes, "_ouvrir", servir(os.urandom(3 * 1024**2)))
    assert installation_pilotes.telecharger_nvidia(derniere(), lambda _part: None, lambda: True) is None
    assert list(installation_pilotes.dossier().iterdir()) == []  # rien de laissé à moitié


@pytest.mark.parametrize("contenu, taille", [(b"x" * 10, 20), (b"", 0), (b"x", 4 * 1024**3)])
def test_telecharger_nvidia_refuse_un_fichier_inattendu(monkeypatch, contenu, taille):
    monkeypatch.setattr(installation_pilotes, "_ouvrir", servir(contenu, taille))
    with pytest.raises(ValueError):
        installation_pilotes.telecharger_nvidia(derniere(), lambda _part: None, lambda: False)
    assert not any(installation_pilotes.dossier().glob("*.exe"))


def test_telecharger_seulement_depuis_nvidia():
    with pytest.raises(ValueError):  # et le réseau n'est jamais utilisé (garde-fou de tests/conftest.py)
        installation_pilotes.telecharger_nvidia(derniere("https://exemple.com/Windows/621.01/pilote.exe"),
                                                lambda _part: None, lambda: False)


def test_script(tmp_path):
    paquet = tmp_path / "O'Brien" / "621.01.exe"  # une apostrophe dans le chemin ne casse pas le script
    texte = installation_pilotes.script([ID_GARMIN], paquet, tmp_path / "etat.json")
    assert texte.startswith(f"$ids = @('{ID_GARMIN}')\n$paquet = '{tmp_path}\\O''Brien\\621.01.exe'\n"
                            f"$etat = '{tmp_path}\\etat.json'\n")
    assert "$paquet = ''" in installation_pilotes.script([], None, tmp_path / "etat.json")


@pytest.mark.parametrize("identifiant", ["'); Remove-Item C:\\ -Recurse; ('", "pas-un-identifiant", ""])
def test_script_refuse_un_identifiant_invalide(tmp_path, identifiant):
    with pytest.raises(ValueError):
        installation_pilotes.script([identifiant], None, tmp_path / "etat.json")


def test_lancer(monkeypatch):
    lancements = []
    monkeypatch.setattr(installation_pilotes, "_lancer_en_administrateur",
                        lambda fichier, parametres, fenetre: lancements.append((fichier, parametres, fenetre)) or 1234)
    installation_pilotes.dossier().mkdir(parents=True)
    installation_pilotes.fichier_etat().write_text("{}")  # état d'une installation précédente : effacé
    paquet = installation_pilotes.dossier() / "621.01.exe"
    assert installation_pilotes.lancer([ID_GARMIN], paquet, 777) == 1234
    assert not installation_pilotes.fichier_etat().exists()
    ((fichier, parametres, fenetre),) = lancements
    assert fenetre == 777  # la demande d'autorisation s'affiche devant la fenêtre de l'application
    assert fichier == "powershell.exe" and parametres.startswith("-NoProfile -NonInteractive -ExecutionPolicy Bypass ")
    script = base64.b64decode(parametres.rsplit(" ", 1)[1]).decode("utf-16-le")
    assert script == installation_pilotes.script([ID_GARMIN], paquet, installation_pilotes.fichier_etat())


def test_lire_etat():
    assert installation_pilotes.lire_etat() == {}
    installation_pilotes.dossier().mkdir(parents=True)
    installation_pilotes.fichier_etat().write_bytes('\ufeff{"fini":true,"etape":""}'.encode())  # écrit par PowerShell
    assert installation_pilotes.lire_etat() == {"fini": True, "etape": ""}


def test_bilan_tout_installe(monkeypatch):
    monkeypatch.setattr(installation_pilotes, "version_nvidia_installee", lambda _carte: "621.01")
    etat = {"fini": True, "windows_update": {"installees": 1, "redemarrage": False}, "nvidia": {"code": 0}}
    assert installation_pilotes.bilan(etat, GARMIN, nvidia_verifie()) == {
        "installes": ["1 pilote de Windows Update", "pilote NVIDIA 621.01"], "echecs": [], "redemarrage": False}


def test_bilan_nvidia_apres_redemarrage(monkeypatch):
    """Installé (code 0), mais le registre donne encore l'ancienne version : Windows la changera au redémarrage."""
    monkeypatch.setattr(installation_pilotes, "version_nvidia_installee", lambda _carte: "617.14")
    resultat = installation_pilotes.bilan({"fini": True, "nvidia": {"code": 0}}, [], nvidia_verifie())
    assert resultat == {"installes": ["pilote NVIDIA 621.01"], "echecs": [], "redemarrage": True}


@pytest.mark.parametrize("etat", [{"fini": True, "windows_update": {"erreur": "0x80240022"},
                                   "nvidia": {"erreur": "Le fichier téléchargé n'est pas signé par NVIDIA"}},
                                  {"fini": True, "windows_update": {"installees": 0}, "nvidia": {"code": -522190823}},
                                  {}])
def test_bilan_echecs(monkeypatch, etat):
    monkeypatch.setattr(installation_pilotes, "version_nvidia_installee", lambda _carte: "617.14")
    resultat = installation_pilotes.bilan(etat, GARMIN, nvidia_verifie())
    assert resultat["installes"] == [] and len(resultat["echecs"]) == 2 and not resultat["redemarrage"]
    assert resultat["echecs"][-1] == "Le pilote NVIDIA n'a pas pu être installé."


def test_bilan_en_partie(monkeypatch):
    deux = GARMIN + [{"id": "3fba6339-e495-4335-8575-5e211ed4522b", "nom": "Autre"}]
    etat = {"fini": True, "windows_update": {"installees": 1, "redemarrage": True}}
    assert installation_pilotes.bilan(etat, deux, None) == {
        "installes": ["1 pilote de Windows Update"], "echecs": ["1 pilote de Windows Update n'a pas pu être installé."],
        "redemarrage": True}


def test_nettoyer():
    installation_pilotes.dossier().mkdir(parents=True)
    (installation_pilotes.dossier() / "621.01.exe").write_bytes(b"x")
    installation_pilotes.nettoyer()
    assert not installation_pilotes.dossier().exists()
