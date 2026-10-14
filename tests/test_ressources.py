"""Tests du module ressources. Lancer avec : python -m pytest"""

import psutil

from modules import ressources

MO = 1024**2


def proc(nom, mo):
    return nom, mo * MO


def test_regroupe_par_nom_et_trie():
    processus = [proc("chrome.exe", 300), proc("code.exe", 500), proc("chrome.exe", 400),
                 proc("explorer.exe", 100)]
    assert ressources.plus_gourmands(processus) == [
        {"nom": "chrome.exe", "octets": 700 * MO}, {"nom": "code.exe", "octets": 500 * MO},
        {"nom": "explorer.exe", "octets": 100 * MO}]


def test_ignore_le_processus_sans_nom():
    processus = [proc("", 50), proc("notepad.exe", 20)]
    assert ressources.plus_gourmands(processus) == [{"nom": "notepad.exe", "octets": 20 * MO}]


def test_photo_du_systeme_coherente_avec_psutil():
    processus = ressources.memoire_par_processus()
    noms = {nom for nom, _ in processus}
    assert "System" in noms and "python.exe" in {n.lower() for n in noms}
    assert abs(len(processus) - len(psutil.pids())) < 20  # des processus naissent et meurent entre-temps


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
    assert resultat["installee"] >= resultat["ram"]["total"]  # une part est réservée au matériel
    assert len(resultat["constats"]) == 3
