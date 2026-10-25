"""Tests du module ressources. Lancer avec : python -m pytest"""

from collections import namedtuple
from types import SimpleNamespace

import psutil
import pytest

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


def test_charge_sans_l_application(monkeypatch):
    """Le travail de l'application elle-même (analyse des dossiers en parallèle) n'est pas compté."""
    Systeme = namedtuple("Systeme", "user system idle")
    Application = namedtuple("Application", "user system")
    systeme = iter([Systeme(10, 10, 80), Systeme(40, 20, 140)])  # 100 s de processeur, dont 40 occupées
    application = iter([Application(1, 1), Application(9, 3)])  # dont 10 par l'application
    monkeypatch.setattr(ressources.psutil, "cpu_times", lambda: next(systeme))
    monkeypatch.setattr(ressources.psutil, "Process", lambda: SimpleNamespace(cpu_times=lambda: next(application)))
    monkeypatch.setattr(ressources.time, "sleep", lambda _: None)
    assert ressources.charge_processeur(3) == pytest.approx(30)
