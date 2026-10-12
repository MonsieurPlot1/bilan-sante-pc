"""Tests du module ressources. Lancer avec : python -m pytest"""

from types import SimpleNamespace

from modules import ressources

MO = 1024**2


def proc(nom, mo):
    memoire = None if mo is None else SimpleNamespace(rss=mo * MO)
    return SimpleNamespace(info={"name": nom, "memory_info": memoire})


def test_regroupe_par_nom_et_trie():
    processus = [proc("chrome.exe", 300), proc("code.exe", 500), proc("chrome.exe", 400),
                 proc("explorer.exe", 100)]
    assert ressources.plus_gourmands(processus) == [
        {"nom": "chrome.exe", "octets": 700 * MO}, {"nom": "code.exe", "octets": 500 * MO},
        {"nom": "explorer.exe", "octets": 100 * MO}]


def test_ignore_les_processus_inaccessibles():
    # AccessDenied : psutil met None à la place de la valeur.
    processus = [proc("System", None), proc(None, 50), proc("notepad.exe", 20)]
    assert ressources.plus_gourmands(processus) == [{"nom": "notepad.exe", "octets": 20 * MO}]


def test_garde_les_5_premiers():
    processus = [proc(f"p{i}.exe", i) for i in range(1, 9)]
    noms = [p["nom"] for p in ressources.plus_gourmands(processus)]
    assert noms == ["p8.exe", "p7.exe", "p6.exe", "p5.exe", "p4.exe"]


def test_scan_reel(monkeypatch):
    monkeypatch.setattr(ressources, "DUREE_MESURE_CPU", 0.1)
    resultat = ressources.scan()
    assert 0 < resultat["ram"]["utilise"] <= resultat["ram"]["total"]
    assert 0 <= resultat["cpu"] <= 100
    assert 0 < len(resultat["processus"]) <= 5
    assert len(resultat["constats"]) == 2
