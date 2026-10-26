"""Tests du bouton « Mettre à jour », sans réseau et sans rien installer. Lancer avec : python -m pytest"""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog

import config
from modules import mise_a_jour
from tests.test_interface import app, corbeille_protegee, fenetre, rien_ne_s_ouvre  # noqa: F401 (fixtures)
from tests.test_mise_a_jour import reseau_et_lancement_interdits, version  # noqa: F401 (fixture)
from tests.test_page_stockage import attendre
from ui import fenetre as fenetre_module

NOUVELLE = mise_a_jour.plus_recente([version("v99.0.0", notes="- Une nouveauté.")], config.VERSION)


class Feuilles(list):
    """Les confirmations montrées, et la réponse à leur donner (confirmée par défaut)."""
    reponse = QDialog.DialogCode.Accepted


@pytest.fixture
def feuilles(monkeypatch):
    montrees = Feuilles()
    monkeypatch.setattr(fenetre_module.Feuille, "exec", lambda feuille: montrees.append(feuille) or montrees.reponse)
    return montrees


def signalee(fenetre, monkeypatch, nouvelle=NOUVELLE) -> None:
    """La recherche du lancement trouve `nouvelle` (None : déjà à jour ou hors ligne)."""
    monkeypatch.setattr(mise_a_jour, "verifier", lambda: nouvelle)
    fenetre.verifier_mise_a_jour()
    attendre(lambda: fenetre.recherche.isFinished())
    attendre(lambda: fenetre.nouvelle_version == nouvelle, 500)


def test_rien_tant_qu_aucune_version_n_est_publiee(fenetre, monkeypatch):
    assert fenetre.bouton_maj.isHidden()
    signalee(fenetre, monkeypatch, None)
    assert fenetre.bouton_maj.isHidden() and fenetre.annonce.texte() == ""


def test_nouvelle_version_signalee(fenetre, monkeypatch):
    signalee(fenetre, monkeypatch)
    assert not fenetre.bouton_maj.isHidden()
    assert fenetre.bouton_maj.toolTip() == f"Version 99.0.0 disponible (tu as la {config.VERSION})"
    assert "99.0.0" in fenetre.annonce.texte()
    fenetre.construire()  # changement de mode clair/sombre : la barre est recréée, le bouton reste
    assert not fenetre.bouton_maj.isHidden()


def test_onglets_toujours_au_milieu(fenetre):
    """Les deux côtés de la barre ont la place du bouton « Mettre à jour », même caché : il n'y a rien à décaler."""
    droite = fenetre.mode.parentWidget()
    assert droite.width() >= fenetre.bouton_maj.sizeHint().width() + 8 + fenetre.mode.sizeHint().width()
    assert droite.width() == fenetre.onglets.parentWidget().layout().itemAtPosition(0, 0).widget().width()


def test_mise_a_jour_telechargee_puis_installee(fenetre, monkeypatch, feuilles):
    signalee(fenetre, monkeypatch)
    installateur = Path(r"C:\App\.mise-a-jour\BilanSantePC-Installation-v99.0.0.exe")
    pendant, lancements, fermetures = [], [], []

    def preparer(fichier, _dossier, progression, _arret):
        assert fichier == NOUVELLE["installateur"]
        progression(0.5)
        pendant.append(fenetre.mode.isEnabled())
        return installateur
    monkeypatch.setattr(mise_a_jour, "installable", lambda _nouvelle: True)
    monkeypatch.setattr(mise_a_jour, "preparer", preparer)
    monkeypatch.setattr(mise_a_jour, "lancer_installation", lambda *arguments: lancements.append(arguments))
    monkeypatch.setattr(fenetre, "close", lambda: fermetures.append(True))
    fenetre.proposer_mise_a_jour()
    (feuille,) = feuilles
    assert feuille.windowTitle() == "Version 99.0.0 disponible"
    assert feuille.texte() == f"Tu as la version {config.VERSION}. Nouveautés :\n• Une nouveauté."
    assert feuille.bouton_confirmer.text() == "Mettre à jour" and feuille.bouton_annuler.text() == "Plus tard"
    assert not fenetre.bouton_maj.isEnabled()
    attendre(lambda: fermetures)
    assert pendant == [False]  # pas de changement de mode pendant le téléchargement
    assert lancements == [(installateur, None)]  # None : dossier de l'application, absent depuis le code source


def test_plus_tard(fenetre, monkeypatch, feuilles):
    signalee(fenetre, monkeypatch)
    monkeypatch.setattr(mise_a_jour, "installable", lambda _nouvelle: True)
    feuilles.reponse = QDialog.DialogCode.Rejected
    fenetre.proposer_mise_a_jour()
    assert fenetre.telechargement is None and fenetre.bouton_maj.isEnabled()


def test_page_de_la_version_si_elle_ne_s_installe_pas_toute_seule(fenetre, monkeypatch, feuilles):
    signalee(fenetre, monkeypatch)
    ouvertes = []
    monkeypatch.setattr(mise_a_jour, "installable", lambda _nouvelle: False)
    monkeypatch.setattr(fenetre, "ouvrir", ouvertes.append)
    fenetre.proposer_mise_a_jour()
    assert feuilles[0].bouton_confirmer.text() == "Ouvrir la page"
    assert ouvertes == [NOUVELLE["page"]] and fenetre.telechargement is None


def test_telechargement_rate(fenetre, monkeypatch, feuilles):
    signalee(fenetre, monkeypatch)

    def preparer(*_):
        raise mise_a_jour.Invalide("Le fichier téléchargé ne correspond pas à celui publié")
    monkeypatch.setattr(mise_a_jour, "installable", lambda _nouvelle: True)
    monkeypatch.setattr(mise_a_jour, "preparer", preparer)
    fenetre.proposer_mise_a_jour()
    attendre(lambda: fenetre.telechargement is None)
    assert fenetre.annonce.texte().startswith("La mise à jour n'a pas pu être téléchargée.")
    assert fenetre.bouton_maj.isEnabled() and fenetre.bouton_maj.text() == " Mettre à jour"
    assert fenetre.mode.isEnabled()
