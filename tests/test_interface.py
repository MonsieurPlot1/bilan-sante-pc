"""Tests de la fenêtre, sans l'afficher à l'écran. Lancer avec : python -m pytest"""

import importlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # avant d'importer Qt : aucune fenêtre visible

import pytest
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication

import historique
from modules import fichiers as module_fichiers
from tests.test_analyse import faux_modules, plante
from tests.test_score import GO, batterie, demarrage, disque, fichiers
from ui import analyse
from ui.fenetre import Fenetre, preparer_application
from ui.widgets import Carte, Fondu, Graphique, Logo
from ui import fenetre as fenetre_module


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


@pytest.fixture(autouse=True)
def rien_ne_s_ouvre(monkeypatch):
    """Aucun test n'ouvre les Paramètres ou un dossier pour de vrai : remplacer os.startfile explicitement."""
    def interdit(*_):
        raise AssertionError("un test a tenté d'ouvrir une page ou un dossier")
    monkeypatch.setattr(os, "startfile", interdit)


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
                 alimentation=plante, batterie=plante)
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

    Renvoie les appels : ("vider", fenêtre) puis ("scan", résultat précédent transmis).
    """
    appels = []
    monkeypatch.setattr(module_fichiers, "corbeille", lambda *_: avant * GO)
    monkeypatch.setattr(module_fichiers, "vider_corbeille", lambda fenetre: appels.append(("vider", fenetre)))

    def scan(precedent=None):
        appels.append(("scan", precedent))
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
    assert appels[0] == ("vider", int(fenetre.winId()))
    assert appels[1][0] == "scan" and appels[1][1]["temporaires"] == 1 * GO
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
    fini = QSignalSpy(fenetre.glissement.finished)
    fenetre.avancer(2, 6, "Disque")
    assert fenetre.progression.maximum() == 600  # en centièmes de partie : la barre glisse
    assert fini.wait(3000)  # attend la vraie fin du glissement : un délai fixe échouait sur un PC chargé
    assert fenetre.progression.value() == 100  # une partie finie
    assert fenetre.info.text() == "Analyse en cours : Disque (2 sur 6)…"


def test_analyse_en_arriere_plan(fenetre, app, monkeypatch):
    """Le vrai thread d'analyse : étapes puis résultat arrivent jusqu'à la fenêtre."""
    faux_modules(monkeypatch)
    fenetre.lancer()
    assert fenetre.phrase.text() == "Analyse de ton PC en cours…" and not fenetre.bouton.isEnabled()
    fenetre.analyse.wait()
    app.processEvents()  # livre les signaux envoyés depuis le thread
    assert fenetre.glissement.endValue() == (len(analyse.MODULES) - 1) * 100  # dernière étape reçue
    assert fenetre.jauge.note == 100 and fenetre.bouton.isEnabled()


def test_bouton_ouvrir_d_un_conseil(fenetre, tmp_path, monkeypatch):
    ouvertures = []
    monkeypatch.setattr(os, "startfile", ouvertures.append)
    faux_modules(monkeypatch, demarrage=lambda: {"constats": ["c"], **demarrage(40)})
    fenetre.afficher(analyse_faite(tmp_path))
    carte = fenetre.liste_conseils.itemAt(0).widget()
    assert carte.bouton.text() == "Ouvrir les Paramètres"
    carte.bouton.click()
    assert ouvertures == ["ms-settings:startupapps"]


def test_ouverture_impossible(fenetre, monkeypatch):
    def echec(_):
        raise OSError("introuvable")
    monkeypatch.setattr(os, "startfile", echec)
    fenetre.ouvrir("ms-settings:inexistant")
    assert fenetre.statusBar().currentMessage() == "Cette page n'a pas pu s'ouvrir sur ce PC."


def test_couleurs_du_theme():
    from ui import theme
    assert isinstance(theme.windows_en_clair(), bool)
    assert theme.rgba("#34d399", 31) == "rgba(52, 211, 153, 31)"  # même rendu qu'avant en thème sombre


def test_icone_de_l_application(app, fenetre):
    from PySide6.QtCore import QSize
    from ui import theme
    assert theme.ICONE_APPLICATION.exists()
    tailles = app.windowIcon().availableSizes()
    assert QSize(16, 16) in tailles and QSize(256, 256) in tailles  # toutes les tailles de l'ico sont lues
    assert not fenetre.findChild(Logo).windowIcon().isNull()  # la même icône en tête de la fenêtre


def test_changer_de_mode(fenetre, app, tmp_path, monkeypatch):
    from ui import theme
    faux_modules(monkeypatch)
    fenetre.afficher(analyse_faite(tmp_path))
    depart = theme.CLAIR
    fenetre.show()  # tailles réelles, pour la position de défilement
    QTest.qWait(10)
    fenetre.pages.currentWidget().verticalScrollBar().setValue(300)
    try:
        fenetre.mode.click()
        QTest.qWait(50)  # le changement se fait juste après le clic, sous le fondu
        assert theme.CLAIR is not depart
        assert theme.mode_choisi() is theme.CLAIR  # choix retenu pour les prochains lancements
        assert fenetre.mode.text().strip() == ("Mode sombre" if theme.CLAIR else "Mode clair")
        assert fenetre.jauge.note == 100 and fenetre.jauge.valeur == 100  # affichée, sans se re-remplir
        assert fenetre.findChild(Fondu, "fondu").isVisible()  # fondu en cours
        QTest.qWait(fenetre_module.DUREE_FONDU + 200)
        assert fenetre.findChild(Fondu, "fondu") is None  # fondu terminé et retiré
        assert fenetre.pages.currentWidget().verticalScrollBar().value() == 300  # on reste au même endroit
        fenetre.lancer()
        assert not fenetre.mode.isEnabled()  # pas de changement pendant l'analyse
        fenetre.analyse.wait()
        app.processEvents()
        assert fenetre.mode.isEnabled()  # de nouveau possible une fois l'analyse finie
    finally:
        theme.fichier_reglages().unlink(missing_ok=True)
        importlib.reload(theme)  # les autres tests retrouvent le mode de Windows


def test_melange_des_couleurs_de_la_barre_de_titre():
    from PySide6.QtGui import QColor
    noir, blanc = QColor("#000000"), QColor("#ffffff")
    assert fenetre_module.melange(noir, blanc, 1.0) == noir  # début du fondu : l'ancienne couleur
    assert fenetre_module.melange(noir, blanc, 0.0) == blanc  # fin : la nouvelle
    assert fenetre_module.melange(noir, blanc, 0.5).red() == 128


def test_detail_qui_se_deplie_et_se_replie(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch, demarrage=lambda: {"constats": ["c"], **demarrage(3)})
    fenetre.afficher(analyse_faite(tmp_path))
    carte = fenetre.cartes["demarrage"]
    carte.bouton.click()
    assert carte.ouvert and not carte.detail.isHidden() and carte.bouton.text() == "Masquer le détail"
    QTest.qWait(400)
    assert carte.detail.height() == carte.hauteur_detail()  # ajusté à ses 3 lignes, sans place vide
    assert Carte.HAUTEUR_DETAIL_MIN <= carte.detail.height() < Carte.HAUTEUR_DETAIL_MAX
    assert carte.detail.topLevelItem(0).toolTip(2) == r"C:\p0.exe"  # texte complet au survol
    carte.bouton.click()
    QTest.qWait(400)
    assert not carte.ouvert and carte.detail.isHidden()


def test_conseils_qui_apparaissent_en_fondu(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch, demarrage=lambda: {"constats": ["c"], **demarrage(40)})
    fenetre.afficher(analyse_faite(tmp_path))
    premiere = fenetre.liste_conseils.itemAt(0).widget()
    assert premiere.graphicsEffect() is not None  # fondu en cours
    QTest.qWait(800)
    assert premiere.graphicsEffect() is None  # effet retiré une fois apparu : texte net


def test_courbe_qui_se_dessine(app):
    graphique = Graphique()
    entrees = [{"date": "2026-10-01T09:00:00", "score": 60}, {"date": "2026-10-02T09:00:00", "score": 70}]
    graphique.afficher(entrees)
    assert graphique.progres < 1
    QTest.qWait(900)
    assert graphique.progres == 1
    graphique.afficher(entrees)  # même historique : pas de nouveau tracé
    assert graphique.progres == 1


def test_bouton_copier_confirme(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch)
    fenetre.afficher(analyse_faite(tmp_path))
    fenetre.copier.click()
    assert fenetre.copier.text().strip() == "Rapport copié"
    QTest.qWait(1800)
    assert fenetre.copier.text().strip() == "Copier le rapport"


def test_molette_qui_glisse(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch)
    fenetre.afficher(analyse_faite(tmp_path))
    fenetre.show()
    QTest.qWait(10)
    zone = fenetre.pages.currentWidget()
    barre = zone.verticalScrollBar()
    cran = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    zone.wheelEvent(cran)
    zone.wheelEvent(cran)  # deux crans rapides s'additionnent
    attendu = min(barre.maximum(), 2 * barre.singleStep() * QApplication.wheelScrollLines())
    assert zone.glissement.endValue() == attendu
    QTest.qWait(400)
    assert barre.value() == attendu

