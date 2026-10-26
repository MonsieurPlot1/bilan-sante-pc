"""Tests de la partie Pilotes de la fenêtre, sans rien télécharger ni installer. Lancer avec : python -m pytest"""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog

from modules import installation_pilotes, score
from tests.test_analyse import faux_modules
from tests.test_fenetre_mise_a_jour import feuilles  # noqa: F401 (fixture)
from tests.test_interface import analyse_faite, app, corbeille_protegee, fenetre, rien_ne_s_ouvre  # noqa: F401
from tests.test_page_stockage import attendre
from tests.test_score import nvidia, pilotes
from ui import analyse
from ui import fenetre as fenetre_module
from ui.widgets import CarteConseil

GARMIN = [{"id": "2fba6339-e495-4335-8575-5e211ed4522b", "nom": "Garmin USB GPS", "date": None}]
PAQUET = Path(r"C:\Pilotes\621.01-notebook.exe")


def analysee(fenetre, monkeypatch, tmp_path, **valeurs) -> None:
    faux_modules(monkeypatch, pilotes=lambda: {"constats": ["constat pilotes"], **pilotes(**valeurs)})
    fenetre.afficher(analyse_faite(tmp_path))


def installation(monkeypatch, etat: dict, relue: str = "621.01") -> list:
    """Remplace le téléchargement et l'installation en administrateur : renvoie la liste des lancements."""
    lancements = []

    def telecharger(_derniere, avance, _arret):
        avance(0.5)
        return PAQUET
    monkeypatch.setattr(installation_pilotes, "telecharger_nvidia", telecharger)
    monkeypatch.setattr(installation_pilotes, "lancer",
                        lambda ids, paquet, fenetre: lancements.append((ids, paquet)) or 42)
    monkeypatch.setattr(installation_pilotes, "termine", lambda processus: processus == 42)
    monkeypatch.setattr(installation_pilotes, "lire_etat", lambda: etat)
    monkeypatch.setattr(installation_pilotes, "version_nvidia_installee", lambda _carte: relue)
    return lancements


def test_carte_et_conseil(fenetre, monkeypatch, tmp_path):
    analysee(fenetre, monkeypatch, tmp_path, nvidia=nvidia(), mises_a_jour=GARMIN)
    assert not fenetre.cartes["pilotes"].isHidden() and fenetre.bouton_pilotes.isEnabled()
    assert fenetre.cartes["pilotes"].points.text() == "hors score"
    assert fenetre.cartes["pilotes"].detail.topLevelItem(0).text(2) == "621.01 disponible (NVIDIA)"
    assert fenetre.cartes["pilotes"].detail.topLevelItem(1).text(0) == "Garmin USB GPS"
    conseil = fenetre.findChild(CarteConseil)
    assert conseil.bouton.text() == " Mettre à jour les pilotes"


def test_rien_a_installer(fenetre, monkeypatch, tmp_path):
    analysee(fenetre, monkeypatch, tmp_path, nvidia=nvidia(derniere="617.14"))
    assert fenetre.bouton_pilotes.isHidden()  # pas de bouton grisé qui ne servirait à rien


def test_le_conseil_demande_confirmation(fenetre, monkeypatch, tmp_path, feuilles):
    analysee(fenetre, monkeypatch, tmp_path, nvidia=nvidia(), mises_a_jour=GARMIN)
    lancements = installation(monkeypatch, {})
    feuilles.reponse = QDialog.DialogCode.Rejected
    fenetre.ouvrir(score.ACTION_PILOTES)  # bouton du conseil : rien n'est ouvert avec os.startfile (fixture)
    (feuille,) = feuilles
    assert feuille.windowTitle() == "Mettre à jour les pilotes ?"
    assert feuille.texte().startswith("• Pilote NVIDIA 621.01, téléchargé depuis le site de NVIDIA")
    assert feuille.texte().endswith("• Garmin USB GPS, par Windows Update")
    assert "l'écran peut clignoter" in feuille.details()
    assert lancements == [] and fenetre.pilotes_a_installer is None and fenetre.mode.isEnabled()


def test_installation_windows_update(fenetre, monkeypatch, tmp_path, feuilles):
    analysee(fenetre, monkeypatch, tmp_path, mises_a_jour=GARMIN)
    lancements = installation(monkeypatch, {"fini": True, "windows_update": {"installees": 1, "redemarrage": False}})
    fenetre.mettre_a_jour_pilotes()
    assert "l'écran peut clignoter" not in feuilles[0].details()  # pas de pilote graphique
    assert lancements == [([GARMIN[0]["id"]], None)]  # rien à télécharger : installation tout de suite
    attendre(lambda: fenetre.pilotes_a_installer is None)
    assert fenetre.annonce.texte().startswith("Installé : 1 pilote de Windows Update.")
    assert fenetre.bouton_pilotes.isHidden()  # à jour jusqu'à la prochaine analyse
    assert fenetre.mode.isEnabled()
    fenetre.mettre_a_jour_pilotes()  # le bouton du conseil, encore là
    assert len(feuilles) == 1 and "relance l'analyse" in fenetre.annonce.texte()


def test_installation_nvidia_puis_redemarrage(fenetre, monkeypatch, tmp_path, feuilles):
    analysee(fenetre, monkeypatch, tmp_path, nvidia=nvidia())
    lancements = installation(monkeypatch, {"fini": True, "nvidia": {"code": 0}}, relue="617.14")
    pendant = []
    monkeypatch.setattr(installation_pilotes, "termine",
                        lambda processus: pendant.append(fenetre.mode.isEnabled()) or processus == 42)
    fenetre.mettre_a_jour_pilotes()
    attendre(lambda: fenetre.pilotes_a_installer is None)
    assert lancements == [([], PAQUET)]
    assert pendant and not any(pendant)  # pas de changement de mode pendant l'installation
    redemarrer = feuilles[-1]
    assert redemarrer.windowTitle() == "Redémarre le PC pour finir"
    assert redemarrer.texte() == "Installé : pilote NVIDIA 621.01."


def test_autorisation_refusee(fenetre, monkeypatch, tmp_path, feuilles):
    analysee(fenetre, monkeypatch, tmp_path, mises_a_jour=GARMIN)

    def refuse(_ids, _paquet, _fenetre):
        raise installation_pilotes.Annulee()
    monkeypatch.setattr(installation_pilotes, "lancer", refuse)
    fenetre.mettre_a_jour_pilotes()
    assert fenetre.annonce.texte().startswith("Mise à jour des pilotes annulée")
    assert fenetre.bouton_pilotes.isEnabled() and fenetre.mode.isEnabled()  # on peut réessayer


def test_telechargement_rate(fenetre, monkeypatch, tmp_path, feuilles):
    analysee(fenetre, monkeypatch, tmp_path, nvidia=nvidia())
    lancements = installation(monkeypatch, {})

    def rate(*_):
        raise OSError("hors ligne")
    monkeypatch.setattr(installation_pilotes, "telecharger_nvidia", rate)
    fenetre.mettre_a_jour_pilotes()
    attendre(lambda: fenetre.pilotes_a_installer is None)
    assert fenetre.annonce.texte().startswith("Le pilote NVIDIA n'a pas pu être téléchargé.")
    assert lancements == [] and fenetre.bouton_pilotes.isEnabled()


@pytest.mark.parametrize("outil, attendu", [({"nom": "MyASUS", "cible": "x"}, "à vérifier avec MyASUS"),
                                            (None, "à vérifier chez le fabricant")])
def test_lignes_pilotes(outil, attendu):
    module = pilotes(nvidia=nvidia(), anciens=2, outil=outil)
    lignes = analyse.lignes_pilotes(module)
    assert lignes[0] == ["NVIDIA GeForce RTX 3060", "617.14", "621.01 disponible (NVIDIA)"]
    assert lignes[1] == ["Pilote 0", "1.0 du 16/05/2022", attendu]
