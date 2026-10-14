"""Tests de la fenêtre, sans l'afficher à l'écran. Lancer avec : python -m pytest"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # avant d'importer Qt : aucune fenêtre visible

import pytest
from PySide6.QtWidgets import QApplication

import historique
from modules import fichiers as module_fichiers
from tests.test_analyse import faux_modules, plante
from tests.test_score import GO, batterie, demarrage, disque, fichiers
from ui import analyse
from ui.fenetre import Fenetre, preparer_application


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    preparer_application(application)
    return application


@pytest.fixture(autouse=True)
def corbeille_protegee(monkeypatch):
    """Aucun test ne doit vider la vraie Corbeille : il faut remplacer vider_corbeille explicitement."""
    def interdit(*_):
        raise AssertionError("un test a tenté de vider la vraie Corbeille")
    monkeypatch.setattr(module_fichiers, "vider_corbeille", interdit)


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
    assert fenetre.jauge.note == analyse.score_global(resultat) == 0 + 6 + 25 + 15
    assert fenetre.etat.text() == "À améliorer" and fenetre.etat.property("niveau") == "rouge"
    assert fenetre.cartes["demarrage"].points.text() == "0 / 30"
    assert fenetre.cartes["fichiers"].points.text() == "hors score"
    assert fenetre.cartes["fichiers"].barre.isHidden() and not fenetre.cartes["disque"].barre.isHidden()
    assert fenetre.cartes["batterie"].isHidden()  # PC fixe
    assert fenetre.liste_conseils.count() == len(analyse.conseils(resultat)) == 2
    assert fenetre.copier.isEnabled() and fenetre.enregistrer.isEnabled()
    assert fenetre.statusBar().currentMessage().startswith("Terminé en")

    fenetre.afficher(resultat)  # relancer ne doit pas empiler les conseils
    assert fenetre.liste_conseils.count() == 2


def test_tous_les_modules_en_erreur(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch, demarrage=plante, disque=plante, fichiers=plante, ressources=plante, redemarrage=plante,
                 batterie=plante)
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


def corbeille_simulee(monkeypatch, avant: float, apres: float) -> list:
    """Corbeille de `avant` Go, qui en contient `apres` une fois la confirmation de Windows passée.

    Renvoie les appels : ("vider", fenêtre) puis ("scan", taille des temporaires transmise).
    """
    appels = []
    monkeypatch.setattr(module_fichiers, "corbeille", lambda *_: avant * GO)
    monkeypatch.setattr(module_fichiers, "vider_corbeille", lambda fenetre: appels.append(("vider", fenetre)))

    def scan(taille_temporaires=None):
        appels.append(("scan", taille_temporaires))
        return {"constats": ["apres"], **fichiers(apres)}
    monkeypatch.setattr(module_fichiers, "scan", scan)
    return appels


def test_vider_la_corbeille(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch, fichiers=lambda: {"constats": ["c"], **fichiers(2, temporaires=1)})
    fenetre.afficher(analyse_faite(tmp_path))
    assert fenetre.vider.isEnabled()
    appels = corbeille_simulee(monkeypatch, avant=2, apres=0)
    fenetre.vider.click()
    # Confirmation de Windows rattachée à notre fenêtre, puis temporaires repris sans les remesurer.
    assert appels == [("vider", int(fenetre.winId())), ("scan", 1 * GO)]
    assert "2,0 Go libérés" in fenetre.statusBar().currentMessage()
    assert fenetre.cartes["fichiers"].resume.text() == "apres"
    assert not fenetre.vider.isEnabled()  # Corbeille vide


def test_vidage_refuse(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch, fichiers=lambda: {"constats": ["c"], **fichiers(2)})
    fenetre.afficher(analyse_faite(tmp_path))
    corbeille_simulee(monkeypatch, avant=2, apres=2)
    fenetre.vider.click()
    assert fenetre.statusBar().currentMessage() == "La Corbeille n'a pas été vidée."
    assert fenetre.cartes["fichiers"].resume.text() == "c" and fenetre.vider.isEnabled()


def test_bouton_grise_si_corbeille_vide(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch)  # Corbeille vide par défaut
    fenetre.afficher(analyse_faite(tmp_path))
    assert not fenetre.vider.isEnabled()


def test_progression_affichee(fenetre):
    fenetre.avancer(2, 6, "Disque")
    assert fenetre.progression.maximum() == 6 and fenetre.progression.value() == 1  # une partie finie
    assert fenetre.info.text() == "Analyse en cours : Disque (2 sur 6)…"


def test_analyse_en_arriere_plan(fenetre, app, monkeypatch):
    """Le vrai thread d'analyse : étapes puis résultat arrivent jusqu'à la fenêtre."""
    faux_modules(monkeypatch)
    fenetre.lancer()
    fenetre.analyse.wait()
    app.processEvents()  # livre les signaux envoyés depuis le thread
    assert fenetre.progression.value() == len(analyse.MODULES) - 1  # dernière étape reçue
    assert fenetre.jauge.note == 100 and fenetre.bouton.isEnabled()
