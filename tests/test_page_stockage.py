"""Tests de l'onglet Stockage, sans l'afficher à l'écran. Lancer avec : python -m pytest"""

import importlib
import os
import time
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from modules import stockage
from tests.test_interface import app, corbeille_protegee, fenetre, rien_ne_s_ouvre  # noqa: F401 (fixtures)
from tests.test_stockage import UTILISE, disque  # noqa: F401 (fixture)
from ui import fenetre as fenetre_module
from ui import stockage as page_stockage
from ui.stockage import HAUTEUR_LIBRE, LigneElement


def resultat_du_faux_disque(racine) -> dict:
    """Ce que la page reçoit à la fin de l'analyse du faux disque."""
    return stockage.scan(str(racine)) | {"date": datetime(2026, 10, 24, 18, 30)}


def attendre(condition, delai: int = 5000) -> None:
    """Laisse Qt tourner jusqu'à ce que `condition()` soit vraie (au plus `delai` millisecondes).

    Pas QTest.qWait : il garde le verrou de Python et le thread d'analyse n'avance presque plus.
    """
    fin = time.monotonic() + delai / 1000
    while not condition():
        assert time.monotonic() < fin, "attente trop longue"
        QApplication.processEvents()
        time.sleep(0.01)  # rend la main au thread d'analyse


def lent(_racine, progression, arret):
    """Analyse qui ne finit que si on l'arrête."""
    progression(1024, 1)
    while not arret():
        time.sleep(0.01)
    return None


def test_onglets(fenetre):
    assert fenetre.pages.currentIndex() == 0
    fenetre.groupe_onglets.button(fenetre_module.ONGLET_STOCKAGE).click()
    assert fenetre.pages.currentIndex() == fenetre.onglet == fenetre_module.ONGLET_STOCKAGE
    fenetre.groupe_onglets.button(0).click()
    voir = next(b for b in fenetre.cartes["disque"].findChildren(QPushButton)
                if b.text() == "Voir ce qui prend de la place")
    voir.click()  # depuis la carte Disque du bilan
    assert fenetre.pages.currentIndex() == fenetre_module.ONGLET_STOCKAGE
    assert fenetre.groupe_onglets.checkedId() == fenetre_module.ONGLET_STOCKAGE


def test_avant_analyse(fenetre):
    page = fenetre.stockage
    assert page.bouton.text().strip() == "Analyser le stockage"
    assert page.categories.isHidden() and page.plus_gros.isHidden()
    assert page.etat.text() in page_stockage.ETATS.values()  # remplissage du disque lu tout de suite


def test_affichage(fenetre, disque):
    page = fenetre.stockage
    page.afficher(resultat_du_faux_disque(disque), animer=False)
    lignes = page.lignes_categories()
    assert len(lignes) == 12
    # Du plus gros au plus petit.
    assert [ligne.categorie["cle"] for ligne in lignes[:3]] == ["systeme", "jeux", "videos"]
    plus_gros = [page.liste_plus_gros.itemAt(i).widget() for i in range(page.liste_plus_gros.count())]
    noms = [ligne.findChildren(page_stockage.TexteCoupe)[0].text() for ligne in plus_gros]
    # Toutes catégories confondues, sauf Système (rien à y faire), dans la limite de NB_PLUS_GROS.
    assert noms == ["Jeu", "film.mkv", "setup.exe", "Editeur", "Windows.old", "Discord", "Discord › Cache", ".ollama"]
    assert page.info.text() == "Analyse du 24/10/2026 à 18:30 : 13 fichiers parcourus en 0 s."
    assert page.bouton.text().strip() == "Relancer l'analyse"


def test_categorie_qui_se_deplie(fenetre, disque):
    page = fenetre.stockage
    page.afficher(resultat_du_faux_disque(disque), animer=False)
    jeux = next(ligne for ligne in page.lignes_categories() if ligne.categorie["cle"] == "jeux")
    assert jeux.detail.maximumHeight() == 0
    QTest.keyClick(jeux, Qt.Key.Key_Space)  # au clavier aussi
    QTest.qWait(350)
    assert jeux.ouvert and jeux.detail.maximumHeight() == HAUTEUR_LIBRE
    assert [e.findChild(QPushButton).text() for e in jeux.detail.findChildren(LigneElement)] == ["Afficher"]
    jeux.basculer()
    QTest.qWait(350)
    assert not jeux.ouvert and jeux.detail.maximumHeight() == 0


def test_afficher_dans_l_explorateur(fenetre, disque, monkeypatch):
    """« Afficher » ouvre seulement l'Explorateur : le dossier, ou celui du fichier avec le fichier choisi."""
    appels = []
    monkeypatch.setattr(os, "startfile", lambda chemin: appels.append(("dossier", chemin)))
    monkeypatch.setattr(page_stockage.subprocess, "Popen", lambda arguments: appels.append(("fichier", arguments)))
    page = fenetre.stockage
    page.afficher(resultat_du_faux_disque(disque), animer=False)
    premier = page.liste_plus_gros.itemAt(0).widget()  # le jeu, un dossier
    premier.findChild(QPushButton).click()
    film = str(disque / "Users" / "moi" / "Videos" / "film.mkv")
    page.montrer(film, dossier=False)
    jeu = str(disque / "Program Files (x86)" / "Steam" / "steamapps" / "common" / "Jeu")
    assert appels == [("dossier", jeu), ("fichier", ["explorer", "/select,", film])]


def test_emplacement_introuvable(fenetre, monkeypatch):
    def refuse(_chemin):
        raise OSError("introuvable")
    monkeypatch.setattr(os, "startfile", refuse)
    fenetre.stockage.montrer(r"C:\nulle\part", dossier=True)
    assert fenetre.statusBar().currentMessage() == "Cet emplacement n'a pas pu s'ouvrir."


def test_analyse_en_arriere_plan(fenetre, app, disque):
    page = fenetre.stockage
    page.racine = str(disque)
    page.lancer()
    assert page.en_cours() and not fenetre.mode.isEnabled()  # pas de changement de mode pendant l'analyse
    assert page.bouton.text().strip() == "Arrêter l'analyse"
    attendre(lambda: page.resultat is not None, 5000)
    assert not page.en_cours() and fenetre.mode.isEnabled()
    assert page.resultat["utilise"] == UTILISE and page.progression.isHidden()
    assert fenetre.statusBar().currentMessage().startswith("Stockage analysé en")


def test_arreter_l_analyse(fenetre, disque, monkeypatch):
    monkeypatch.setattr(stockage, "scan", lent)
    page = fenetre.stockage
    page.lancer()
    page.lancer()  # le même bouton arrête
    assert page.bouton.text().strip() == "Arrêt en cours…" and not page.bouton.isEnabled()
    attendre(lambda: not page.en_cours() and page.bouton.isEnabled(), 5000)
    QTest.qWait(50)
    assert page.resultat is None and page.bouton.text().strip() == "Analyser le stockage"
    assert fenetre.statusBar().currentMessage() == "Analyse du stockage arrêtée."


def test_analyse_en_erreur(fenetre, monkeypatch):
    def plante(*_):
        raise RuntimeError("disque débranché")
    monkeypatch.setattr(stockage, "scan", plante)
    page = fenetre.stockage
    page.lancer()
    attendre(lambda: not page.en_cours() and page.bouton.isEnabled(), 5000)
    QTest.qWait(50)
    assert page.info.text().startswith("L'analyse du stockage n'a pas pu aboutir.")
    assert page.info.objectName() == "erreur" and page.categories.isHidden()


def test_fermer_pendant_l_analyse(fenetre, monkeypatch):
    monkeypatch.setattr(stockage, "scan", lent)
    fenetre.stockage.lancer()
    fenetre.close()  # arrête l'analyse et attend le thread : pas de plantage de Qt
    assert not fenetre.stockage.analyse.isRunning()


def test_resultat_garde_au_changement_de_mode(fenetre, disque):
    from ui import theme
    fenetre.changer_page(fenetre_module.ONGLET_STOCKAGE)
    resultat = resultat_du_faux_disque(disque)
    fenetre.stockage.afficher(resultat, animer=False)
    fenetre.show()
    try:
        fenetre.mode.click()
        QTest.qWait(fenetre_module.DUREE_FONDU + 200)
        assert fenetre.stockage.resultat is resultat and len(fenetre.stockage.lignes_categories()) == 12
        assert fenetre.pages.currentIndex() == fenetre_module.ONGLET_STOCKAGE  # on reste sur l'onglet
    finally:
        theme.fichier_reglages().unlink(missing_ok=True)
        importlib.reload(theme)  # les autres tests retrouvent le mode de Windows


def test_textes():
    assert page_stockage.nombre_lisible(584684) == "584\u202f684"
    assert page_stockage.part_lisible(0, 100) == "0 %" and page_stockage.part_lisible(1, 1000) == "moins de 1 %"
    assert page_stockage.part_lisible(49, 100) == "49 %"
    assert [page_stockage.niveau_remplissage(p) for p in (50, 80, 96)] == ["vert", "orange", "rouge"]
