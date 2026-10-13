"""Tests de la fenêtre, sans l'afficher à l'écran. Lancer avec : python -m pytest"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # avant d'importer Qt : aucune fenêtre visible

import pytest
from PySide6.QtWidgets import QApplication

import historique
from tests.test_analyse import faux_modules, plante
from tests.test_score import batterie, demarrage, disque
from ui import analyse
from ui.fenetre import Fenetre, preparer_application


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    preparer_application(application)
    return application


@pytest.fixture
def fenetre(app, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))  # historique de test, pas celui de l'utilisateur
    resultat = Fenetre()
    yield resultat
    resultat.close()


def analyse_faite(tmp_path) -> dict:
    """Ce que le thread d'analyse envoie à la fenêtre."""
    resultat = analyse.analyser()
    resultat["historique"] = historique.enregistrer(resultat, tmp_path)
    resultat["comparaison"] = historique.comparer(resultat["historique"], analyse.NOMS)
    return resultat


def test_etat_initial(fenetre):
    assert not fenetre.copier.isEnabled() and not fenetre.enregistrer.isEnabled()
    assert fenetre.cartes["batterie"].isHidden()
    assert fenetre.jauge.texte_vide == "–"
    assert "Aucune analyse enregistrée" in fenetre.comparaison.text()


def test_analyse_complete(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch, demarrage=lambda: {"constats": ["c"], **demarrage(40)},
                 disque=lambda: {"constats": ["c"], **disque(90)})
    resultat = analyse_faite(tmp_path)
    fenetre.afficher(resultat)
    assert fenetre.jauge.note == analyse.score_global(resultat) == 0 + 7 + 30
    assert fenetre.etat.text() == "À améliorer" and fenetre.etat.property("niveau") == "rouge"
    assert fenetre.cartes["demarrage"].points.text() == "0 / 35"
    assert fenetre.cartes["batterie"].isHidden()  # PC fixe
    assert fenetre.liste_conseils.count() == len(analyse.conseils(resultat)) == 2
    assert fenetre.copier.isEnabled() and fenetre.enregistrer.isEnabled()
    assert fenetre.statusBar().currentMessage().startswith("Terminé en")

    fenetre.afficher(resultat)  # relancer ne doit pas empiler les conseils
    assert fenetre.liste_conseils.count() == 2


def test_tous_les_modules_en_erreur(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch, demarrage=plante, disque=plante, ressources=plante, batterie=plante)
    fenetre.afficher(analyse_faite(tmp_path))
    assert fenetre.jauge.note is None and fenetre.jauge.texte_vide == "?"
    assert fenetre.etat.text() == "Analyse incomplète"
    assert all(carte.points.text() == "erreur" for carte in fenetre.cartes.values())
    assert "pas enregistrée" in fenetre.comparaison.text()


def test_batterie_affichee(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch, batterie=lambda: {"constats": ["b"], **batterie(0.5)})
    fenetre.afficher(analyse_faite(tmp_path))
    assert not fenetre.cartes["batterie"].isHidden()
    assert fenetre.cartes["batterie"].points.text() == "4 / 15"



def test_famille_de_police(monkeypatch):
    from ui import theme
    # La plateforme hors écran des tests ne voit aucune police : on simule celles installées.
    monkeypatch.setattr(theme.QFontDatabase, "hasFamily", lambda nom: nom == "Segoe UI")
    theme.famille.cache_clear()
    try:
        assert theme.famille(("Segoe UI Variable Text", "Segoe UI")) == "Segoe UI"
        assert theme.famille(("Segoe Fluent Icons", "Segoe MDL2 Assets")) == "Segoe MDL2 Assets"
    finally:
        theme.famille.cache_clear()  # ne pas garder ce faux résultat pour les autres tests
