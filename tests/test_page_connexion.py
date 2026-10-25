"""Tests de l'onglet Connexion, sans l'afficher à l'écran et sans réseau. Lancer avec : python -m pytest"""

import importlib
import os
import time
from datetime import datetime

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QPushButton

from modules import connexion
from tests.test_connexion import liaison, mesures, reseau_interdit  # noqa: F401 (fixture)
from tests.test_interface import app, corbeille_protegee, fenetre, rien_ne_s_ouvre  # noqa: F401 (fixtures)
from tests.test_page_stockage import attendre
from ui import fenetre as fenetre_module
from ui.widgets import CarteConseil


@pytest.fixture(autouse=True)
def liaison_fixe(monkeypatch):
    """La page relit la liaison à chaque visite : une liaison fixe, pour des tests qui ne dépendent pas du PC."""
    monkeypatch.setattr(connexion, "liaison", liaison)


def resultat(**valeurs) -> dict:
    """Ce que le test de connexion renvoie à la page."""
    r = mesures(**valeurs) | {"duree": 15.2, "date": datetime(2026, 10, 25, 17, 5)}
    r["usages"] = [(usage, condition(r)) for usage, condition in connexion.USAGES]
    r["conseils"] = connexion.conseils(r)
    return r


def faux_scan(*resultats):
    """Test qui annonce ses étapes puis renvoie `resultat` (ou lève l'exception donnée)."""
    def scan(progression, _arret):
        for etape in ("ping", "descendant", "montant"):
            progression(etape, 1.0, 20.0)
        if isinstance(resultats[0], Exception):
            raise resultats[0]
        return resultats[0]
    return scan


def lent(progression, arret):
    """Test qui ne finit que si on l'arrête."""
    progression("descendant", 0.5, 300.0)
    while not arret():
        time.sleep(0.01)
    return None


def textes(disposition) -> list[str]:
    return [label.text() for i in range(disposition.count()) for label in
            disposition.itemAt(i).widget().findChildren(QLabel)]


def test_onglet(fenetre):
    fenetre.groupe_onglets.button(fenetre_module.ONGLET_CONNEXION).click()
    assert fenetre.pages.currentIndex() == fenetre.onglet == fenetre_module.ONGLET_CONNEXION


def test_avant_le_test(fenetre):
    page = fenetre.connexion
    assert page.etat.text() == "Pas encore testée" and page.bouton.text().strip() == "Lancer le test"
    assert all(section.isHidden() for section in page.sections)
    assert {compteur.valeur.text() for compteur in page.compteurs.values()} == {"–"}


def test_test_complet(fenetre, monkeypatch):
    monkeypatch.setattr(connexion, "scan", faux_scan(resultat(descendant=512, montant=255.4, ping=19.6)))
    page = fenetre.connexion
    page.lancer()
    assert page.en_cours() and not fenetre.mode.isEnabled()  # pas de changement de mode pendant le test
    assert page.bouton.text().strip() == "Arrêter le test" and page.etat.text() == "Test en cours"
    attendre(lambda: not page.en_cours())
    assert fenetre.mode.isEnabled() and page.progression.isHidden()
    assert page.etat.text() == "Très rapide" and page.bouton.text().strip() == "Relancer le test"
    assert [c.valeur.text() for c in page.compteurs.values()] == ["512", "255", "20"]
    assert page.compteurs["descendant"].accessibleName() == "Téléchargement : 512 Mbit/s"
    assert page.info.text() == "Test du 25/10/2026 à 17:05 avec le serveur de Cloudflare le plus proche, en 15 s."
    assert not any(section.isHidden() for section in page.sections) and page.remarque.isHidden()
    assert textes(page.liste_usages).count("Oui") == len(connexion.USAGES)
    assert textes(page.liste_conseils) == ["Rien à signaler : rien ne freine ta connexion."]
    assert "78 % (bon)" in textes(page.liste_liaison)


def test_progression(fenetre):
    page = fenetre.connexion
    page.avancer(("descendant", 0.5, 487.3))
    assert page.compteurs["descendant"].valeur.text() == "487" and page.info.text() == "Mesure du téléchargement…"
    assert page.glissement.endValue() == 325  # au milieu de l'étape du téléchargement (100 à 550)
    page.avancer(("ping", 0.3, 21.4))
    assert page.compteurs["ping"].valeur.text() == "21"


def test_connexion_lente(fenetre):
    page = fenetre.connexion
    page.afficher(resultat(descendant=6.3, montant=0.9, ping=128, gigue=41, trafic=4.2,
                           lien=liaison(signal=32, bande="2,4 GHz", vitesse=72)), animer=False)
    assert page.etat.text() == "Lente" and page.etat.property("niveau") == "rouge"
    assert page.compteurs["descendant"].valeur.text() == "6,3"
    assert not page.remarque.isHidden() and page.remarque.text().startswith("D'autres programmes")
    cartes = [page.liste_conseils.itemAt(i).widget() for i in range(page.liste_conseils.count())]
    assert len(cartes) == 3 and all(isinstance(carte, CarteConseil) for carte in cartes)
    assert textes(page.liste_usages).count("Difficile") == 4


def test_conseil_ouvre_les_parametres(fenetre, monkeypatch):
    ouverts = []
    monkeypatch.setattr(os, "startfile", ouverts.append)
    page = fenetre.connexion
    page.afficher(resultat(lien=liaison(bande="2,4 GHz")), animer=False)
    (carte,) = [page.liste_conseils.itemAt(i).widget() for i in range(page.liste_conseils.count())]
    carte.bouton.click()
    assert ouverts == ["ms-settings:network-wifi"]  # seulement ouvrir la page, rien n'est changé


def test_test_impossible(fenetre, monkeypatch):
    erreur = "Ton PC n'est relié à aucun réseau : active le Wi-Fi ou branche un câble, puis relance le test."
    monkeypatch.setattr(connexion, "scan", faux_scan({"liaison": liaison(None, None), "erreur": erreur}))
    page = fenetre.connexion
    page.afficher(resultat(), animer=False)  # un ancien résultat disparaît : il tromperait
    page.lancer()
    attendre(lambda: not page.en_cours())
    QTest.qWait(50)
    assert page.etat.text() == "Test impossible" and page.info.text() == erreur
    assert page.info.objectName() == "erreur" and all(section.isHidden() for section in page.sections)
    assert page.resultat is None and "Aucune" in textes(page.liste_liaison)
    assert fenetre.annonce.texte() == "Le test de connexion n'a pas pu aboutir."


def test_panne_imprevue(fenetre, monkeypatch):
    monkeypatch.setattr(connexion, "scan", faux_scan(RuntimeError("panne")))
    page = fenetre.connexion
    page.lancer()
    attendre(lambda: not page.en_cours())
    assert page.info.text().startswith("Le test de connexion n'a pas pu aboutir.")


def test_arreter_le_test(fenetre, monkeypatch):
    monkeypatch.setattr(connexion, "scan", lent)
    page = fenetre.connexion
    page.lancer()
    page.lancer()  # le même bouton arrête
    assert page.bouton.text().strip() == "Arrêt en cours…" and not page.bouton.isEnabled()
    attendre(lambda: not page.en_cours() and page.bouton.isEnabled())
    QTest.qWait(50)
    assert page.resultat is None and page.bouton.text().strip() == "Lancer le test"
    assert fenetre.annonce.texte() == "Test de connexion arrêté."


def test_fermer_pendant_le_test(fenetre, monkeypatch):
    monkeypatch.setattr(connexion, "scan", lent)
    fenetre.connexion.lancer()
    fenetre.close()  # arrête le test et attend le thread : pas de plantage de Qt
    assert not fenetre.connexion.travail.isRunning()


def test_liaison_lue_a_chaque_visite(fenetre, monkeypatch):
    page = fenetre.connexion
    page.lire_liaison()
    attendre(lambda: not page.lecture.isRunning())
    QTest.qWait(20)
    assert textes(page.liste_liaison)[:2] == ["Connexion", "Wi-Fi"]

    def illisible():
        raise OSError("service Wi-Fi arrêté")
    monkeypatch.setattr(connexion, "liaison", illisible)
    page.lire_liaison()
    attendre(lambda: not page.lecture.isRunning())
    QTest.qWait(20)
    assert textes(page.liste_liaison) == ["Connexion", "Windows n'a pas pu donner les informations.", "Inconnue"]


def test_resultat_garde_au_changement_de_mode(fenetre):
    from ui import theme
    fenetre.changer_page(fenetre_module.ONGLET_CONNEXION)
    fait = resultat()
    fenetre.connexion.afficher(fait, animer=False)
    fenetre.show()
    try:
        fenetre.mode.click()
        QTest.qWait(fenetre_module.DUREE_FONDU + 200)
        assert fenetre.connexion.resultat is fait and fenetre.connexion.etat.text() == "Très rapide"
        assert fenetre.pages.currentIndex() == fenetre_module.ONGLET_CONNEXION  # on reste sur l'onglet
    finally:
        theme.fichier_reglages().unlink(missing_ok=True)
        importlib.reload(theme)  # les autres tests retrouvent le mode de Windows


def test_aide_ouvre_les_parametres_reseau(fenetre, monkeypatch):
    ouverts = []
    monkeypatch.setattr(os, "startfile", ouverts.append)
    lien = next(b for b in fenetre.connexion.findChildren(QPushButton) if b.text() == "Ouvrir les paramètres réseau")
    lien.click()
    assert ouverts == ["ms-settings:network-status"]
