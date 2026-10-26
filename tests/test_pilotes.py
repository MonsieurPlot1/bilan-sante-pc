"""Tests du module pilotes, sans réseau ni PowerShell (voir tests/conftest.py). Lancer avec : python -m pytest"""

import json
from datetime import date

import pytest

from modules import pilotes

PRODUITS = b"""<?xml version="1.0" encoding="utf-8"?>
<LookupValueSearch><LookupValues>
  <LookupValue ParentID="120"><Name>GeForce RTX 3060</Name><Value>933</Value></LookupValue>
  <LookupValue ParentID="123"><Name>GeForce RTX 3060 Laptop GPU</Name><Value>940</Value></LookupValue>
</LookupValues></LookupValueSearch>"""
URL = "https://fr.download.nvidia.com/Windows/621.01/621.01-notebook-win10-win11-64bit-international-dch-whql.exe"


def reponse_nvidia(version: str = "621.01", url: str = URL) -> bytes:
    return json.dumps({"Success": "1", "IDS": [{"downloadInfo": {
        "Version": version, "ReleaseDateTime": "2026 octobre 21", "DownloadURL": url,
        "DownloadURLFileSize": "1.04 GB"}}]}).encode()


def carte(version: str = "32.0.16.1714") -> dict:
    return {"nom": "NVIDIA GeForce RTX 3060 Laptop GPU", "categorie": "Carte graphique", "fournisseur": "NVIDIA",
            "version": version, "date": date(2026, 9, 17), "age": 39}


@pytest.mark.parametrize("windows, attendu", [("32.0.16.1714", "617.14"), ("31.0.15.5222", "552.22"),
                                              ("32.0.15.6094", "560.94"), ("27.21.14.5671", "456.71"),
                                              ("", None), ("abc", None), ("1.2.3", None)])
def test_version_nvidia(windows, attendu):
    """Les 5 derniers chiffres des deux derniers nombres : 16.1714 -> 617.14."""
    assert pilotes.version_nvidia(windows) == attendu


def test_plus_recente():
    assert pilotes.plus_recente("621.01", "617.14") and pilotes.plus_recente("617.140", "617.14")
    assert not pilotes.plus_recente("617.14", "617.14") and not pilotes.plus_recente("99.9", "617.14")


def test_numeros_produit():
    assert pilotes.numeros_produit(PRODUITS, "NVIDIA GeForce RTX 3060 Laptop GPU") == ("123", "940")
    assert pilotes.numeros_produit(PRODUITS, "NVIDIA GeForce RTX 3060") == ("120", "933")  # pas la version portable
    assert pilotes.numeros_produit(PRODUITS, "NVIDIA GeForce RTX 9090") is None


def test_date_et_taille_nvidia():
    assert pilotes.date_nvidia("2026 octobre 21") == date(2026, 10, 21)
    assert pilotes.date_nvidia("2026 août 5") == date(2026, 8, 5)
    assert pilotes.date_nvidia("Tue Oct 21, 2026") is None
    assert pilotes.taille_nvidia("1.04 GB") == round(1.04 * 1024**3)
    assert pilotes.taille_nvidia("990.85 MB") == round(990.85 * 1024**2)
    assert pilotes.taille_nvidia("?") == 0


def test_derniere_nvidia():
    assert pilotes.derniere_nvidia(reponse_nvidia()) == {"version": "621.01", "date": date(2026, 10, 21), "url": URL,
                                                         "taille": round(1.04 * 1024**3)}
    assert pilotes.derniere_nvidia(b'{"Success": "0", "IDS": []}') is None
    with pytest.raises(ValueError):  # jamais un fichier venu d'ailleurs que du site de NVIDIA
        pilotes.derniere_nvidia(reponse_nvidia(url="https://exemple.com/Windows/621.01/pilote.exe"))


def servir(*reponses):
    """Remplace le réseau : chaque appel reçoit la réponse suivante (une exception est levée)."""
    restantes = list(reponses)

    def ouvrir(_url):
        reponse = restantes.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse
    return ouvrir


def test_verifier_nvidia(monkeypatch):
    monkeypatch.setattr(pilotes, "_ouvrir", servir(PRODUITS, reponse_nvidia()))
    resultat = pilotes.verifier_nvidia(carte())
    assert resultat["carte"] == "NVIDIA GeForce RTX 3060 Laptop GPU" and resultat["installee"] == "617.14"
    assert resultat["derniere"]["version"] == "621.01" and pilotes.nvidia_a_installer(resultat)


@pytest.mark.parametrize("reponses", [(OSError("hors ligne"),), (PRODUITS, b"pas du json"), (b"<pas du xml",)])
def test_verifier_nvidia_sans_reponse_utile(monkeypatch, reponses):
    monkeypatch.setattr(pilotes, "_ouvrir", servir(*reponses))
    resultat = pilotes.verifier_nvidia(carte())
    assert resultat["installee"] == "617.14" and resultat["derniere"] is None
    assert not pilotes.nvidia_a_installer(resultat)


def test_nvidia_a_jour(monkeypatch):
    monkeypatch.setattr(pilotes, "_ouvrir", servir(PRODUITS, reponse_nvidia("617.14")))
    assert not pilotes.nvidia_a_installer(pilotes.verifier_nvidia(carte()))


def test_du_pc():
    def pilote(fournisseur):
        return {"fournisseur": fournisseur}
    asus = "ASUSTeK COMPUTER INC."
    assert pilotes.du_pc(pilote("Advanced Micro Devices, Inc."), asus)
    assert pilotes.du_pc(pilote("Realtek Semiconductor Corp."), asus)
    assert pilotes.du_pc(pilote("ASUSTek Computer Inc."), asus)  # le fabricant du PC lui-même
    assert not pilotes.du_pc(pilote("Razer Inc"), asus)  # un accessoire : son propre logiciel le met à jour
    assert not pilotes.du_pc(pilote("ASUSTek Computer Inc."), "")


def test_outil_du_fabricant():
    applis = [{"nom": "Armoury Crate", "id": "B9ECED6F.ArmouryCrate_qmba6cd70vzyy!App"},
              {"nom": "MyASUS", "id": "B9ECED6F.ASUSPCAssistant_qmba6cd70vzyy!App"}]
    assert pilotes.outil_du_fabricant(applis) == {"nom": "MyASUS",
                                                  "cible": r"shell:AppsFolder\B9ECED6F.ASUSPCAssistant_qmba6cd70vzyy!App"}
    assert pilotes.outil_du_fabricant([{"nom": "Steam", "id": "x"}]) is None


def test_interroger_windows(monkeypatch):
    lu = {"mises_a_jour": [{"id": "2fba6339-e495-4335-8575-5e211ed4522b", "titre": "Garmin - Other hardware",
                            "modele": "Garmin USB GPS", "fabricant": "Garmin", "date": "2012-04-19", "taille": 190490}],
          "applis": [{"nom": "MyASUS", "id": "B9ECED6F.ASUSPCAssistant_qmba6cd70vzyy!App"}]}
    monkeypatch.setattr(pilotes, "_powershell", lambda _script: json.dumps(lu))
    resultat = pilotes.interroger_windows()
    assert resultat["mises_a_jour"] == [{"id": "2fba6339-e495-4335-8575-5e211ed4522b", "nom": "Garmin USB GPS",
                                         "titre": "Garmin - Other hardware", "fabricant": "Garmin",
                                         "taille": 190490, "date": date(2012, 4, 19)}]
    assert resultat["outil"]["nom"] == "MyASUS"


@pytest.mark.parametrize("sortie", [json.dumps({"erreur": "Service arrêté", "applis": []}), "pas du json",
                                    OSError("powershell.exe introuvable")])
def test_interroger_windows_en_echec(monkeypatch, sortie):
    def powershell(_script):
        if isinstance(sortie, Exception):
            raise sortie
        return sortie
    monkeypatch.setattr(pilotes, "_powershell", powershell)
    assert pilotes.interroger_windows()["mises_a_jour"] is None  # « non consulté », pas « rien à installer »


def test_pilotes_installes_sur_ce_pc():
    """Lecture réelle du registre de ce PC : seulement des classes qui comptent, sans doublon."""
    trouves = pilotes.pilotes_installes(date(2026, 10, 26))
    assert all(pilote["categorie"] in pilotes.CATEGORIES.values() for pilote in trouves)
    assert len({(pilote["nom"], pilote["version"]) for pilote in trouves}) == len(trouves)
    assert all(pilote["age"] is None or pilote["age"] == (date(2026, 10, 26) - pilote["date"]).days for pilote in trouves)


def nvidia_verifie(derniere: str | None = "621.01") -> dict:
    return {"carte": "NVIDIA GeForce RTX 3060 Laptop GPU", "installee": "617.14",
            "derniere": derniere and {"version": derniere, "date": date(2026, 10, 21), "url": URL, "taille": 10}}


def test_constats():
    garmin = [{"nom": "Garmin USB GPS"}]
    vieux = [{"nom": "Realtek PCIe GbE"}, {"nom": "AMD SMBus"}]
    myasus = {"nom": "MyASUS", "cible": "shell:AppsFolder\\x"}
    assert pilotes.constats(nvidia_verifie(), garmin, True, vieux, myasus, "ASUSTeK COMPUTER INC.") == [
        "NVIDIA GeForce RTX 3060 Laptop GPU : pilote 617.14, la version 621.01 est disponible, sortie le 21/10/2026.",
        "Windows Update propose 1 pilote : Garmin USB GPS.",
        "Windows est réglé pour ne jamais installer de pilotes par Windows Update (réglage souvent posé par un "
        "logiciel d'optimisation ou par une entreprise).",
        "2 pilotes du PC ont plus de 2 ans : MyASUS dit s'il en existe des plus récents."]
    assert pilotes.constats(nvidia_verifie("617.14"), [], False, [], None, "") == [
        "NVIDIA GeForce RTX 3060 Laptop GPU : pilote 617.14, le plus récent.",
        "Windows Update ne propose aucun pilote.", "Les pilotes des composants du PC ont tous moins de 2 ans."]
    assert pilotes.constats(nvidia_verifie(None), None, False, vieux[:1], None, "LENOVO") == [
        "NVIDIA GeForce RTX 3060 Laptop GPU : pilote 617.14 (dernière version non vérifiable : pas de connexion ?).",
        "Windows Update n'a pas pu être consulté.",
        "1 pilote du PC a plus de 2 ans : le site du fabricant du PC (LENOVO) dit s'il en existe des plus récents."]


def test_scan(monkeypatch):
    """Registre réel, Windows Update et NVIDIA remplacés."""
    monkeypatch.setattr(pilotes, "interroger_windows", lambda: {"mises_a_jour": [{"id": "x", "nom": "Garmin"}],
                                                                "outil": None})
    monkeypatch.setattr(pilotes, "verifier_nvidia", lambda carte_: nvidia_verifie() | {"carte": carte_["nom"]})
    resultat = pilotes.scan()
    assert resultat["score"] is None and resultat["constats"]
    assert resultat["a_installer"] == 1 + bool(resultat["nvidia"])  # Garmin, et NVIDIA si le PC en a une
    assert all(ancien["age"] > 730 for ancien in resultat["anciens"])
