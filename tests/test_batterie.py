"""Tests du module batterie. Lancer avec : python -m pytest"""

from types import SimpleNamespace

import pytest

from modules import batterie


def fausse_batterie(monkeypatch, pourcentage=80, branche=True, capacites=None):
    monkeypatch.setattr(batterie.psutil, "sensors_battery",
                        lambda: SimpleNamespace(percent=pourcentage, power_plugged=branche))
    monkeypatch.setattr(batterie, "capacites", lambda: capacites)


def test_pc_fixe_non_applicable(monkeypatch):
    monkeypatch.setattr(batterie.psutil, "sensors_battery", lambda: None)
    assert batterie.scan() == {"applicable": False, "score": None, "constats": []}


def test_usure_mesuree(monkeypatch):
    fausse_batterie(monkeypatch, capacites=(90000, 60000))
    resultat = batterie.scan()
    assert resultat["applicable"] and resultat["sante"] == pytest.approx(2 / 3)
    assert "garde 67 %" in resultat["constats"][1] and "usure : 33 %" in resultat["constats"][1]


def test_usure_non_mesurable(monkeypatch):
    fausse_batterie(monkeypatch, branche=False, capacites=None)
    resultat = batterie.scan()
    assert resultat["sante"] is None
    assert resultat["constats"] == ["Batterie chargée à 80 %, sur batterie.", "Usure non mesurable sur ce PC."]


@pytest.mark.parametrize("origine, actuelle, attendu", [
    (100, 80, 0.8), (100, 105, 1.0), (0, 50, None), (100, 0, None), (100, 200, None)])
def test_sante(origine, actuelle, attendu):
    assert batterie.sante(origine, actuelle) == (pytest.approx(attendu) if attendu else None)


def test_capacites_reelles():
    # Sur un PC sans batterie ou dont le pilote ne donne rien : None, sans planter.
    capacite = batterie.capacites()
    assert capacite is None or (capacite[0] > 0 and capacite[1] > 0)
