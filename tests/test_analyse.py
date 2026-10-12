"""Tests de l'orchestration de l'analyse et du rapport. Lancer avec : python -m pytest"""

import logging
import sys

import pytest

import journal
from tests.test_score import demarrage, disque
from ui import analyse


def faux_modules(monkeypatch, scan_demarrage, scan_disque) -> None:
    (_, nom_dem, _, neutre_dem), (_, nom_dis, _, neutre_dis) = analyse.MODULES
    monkeypatch.setattr(analyse, "MODULES", [("demarrage", nom_dem, scan_demarrage, neutre_dem),
                                             ("disque", nom_dis, scan_disque, neutre_dis)])


def resultat(nb_programmes: int, pourcentage: float):
    return lambda: {"constats": ["constat"], **demarrage(nb_programmes)}, \
           lambda: {"constats": ["constat disque"], **disque(pourcentage)}


def test_analyse_normale(monkeypatch):
    faux_modules(monkeypatch, *resultat(5, 40))
    r = analyse.analyser()
    assert r["erreurs"] == {}
    assert analyse.score_global(r) == 100


def test_un_module_qui_plante_n_empeche_pas_l_autre(monkeypatch):
    def plante():
        raise PermissionError("Access is denied")
    _, scan_disque = resultat(0, 90)
    faux_modules(monkeypatch, plante, scan_disque)
    r = analyse.analyser()
    assert list(r["erreurs"]) == ["demarrage"]
    assert "Démarrage" in r["erreurs"]["demarrage"]
    assert r["bilan"]["scores"]["disque"] == 10  # le disque a quand même été évalué
    assert analyse.score_global(r) is None  # pas de score global trompeur
    rapport = analyse.rapport_texte(r)
    assert "Démarrage : erreur" in rapport and "Disque : 10 / 50" in rapport


@pytest.mark.parametrize("note, niveau", [(100, "vert"), (80, "vert"), (79, "orange"),
                                          (50, "orange"), (49, "rouge"), (0, "rouge"), (None, "gris")])
def test_interpretation(note, niveau):
    assert analyse.interpretation(note)[0] == niveau


def test_rapport_avec_conseils(monkeypatch):
    faux_modules(monkeypatch, *resultat(20, 99))
    rapport = analyse.rapport_texte(analyse.analyser())
    assert "Score : 20 / 100" in rapport
    assert "1. " in rapport and "Conseils :" in rapport


def test_journal_ecrit_dans_le_dossier(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)  # remis en place après le test
    fichier = journal.configurer(tmp_path)
    logging.getLogger("test").info("bonjour")
    logging.shutdown()
    assert fichier == tmp_path / "bilan.log"
    assert "bonjour" in fichier.read_text(encoding="utf-8")
