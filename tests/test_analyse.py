"""Tests de l'orchestration de l'analyse et du rapport. Lancer avec : python -m pytest"""

import logging
import sys
from pathlib import Path

import pytest

import journal
from tests.test_score import GO, batterie, demarrage, disque, redemarrage, ressources
from ui import analyse


def plante():
    raise PermissionError("Access is denied")


def faux_modules(monkeypatch, **scans) -> None:
    """Remplace les scans des modules : par défaut un PC en forme sans batterie."""
    defaut = {"demarrage": lambda: {"constats": ["constat démarrage"], **demarrage(5)},
              "disque": lambda: {"constats": ["constat disque"], **disque(40)},
              "ressources": lambda: {"constats": ["constat ressources"], **ressources()},
              "redemarrage": lambda: {"constats": ["constat redémarrage"], **redemarrage()},
              "batterie": lambda: {"applicable": False, "constats": []}} | scans
    monkeypatch.setattr(analyse, "MODULES", [(cle, nom, defaut[cle]) for cle, nom, _ in analyse.MODULES])


def test_analyse_normale(monkeypatch):
    faux_modules(monkeypatch)
    r = analyse.analyser()
    assert r["erreurs"] == {}
    assert analyse.score_global(r) == 100
    assert "batterie" not in r["modules"]  # PC fixe : la batterie n'apparaît pas


def test_un_module_qui_plante_n_empeche_pas_les_autres(monkeypatch):
    faux_modules(monkeypatch, demarrage=plante, disque=lambda: {"constats": [], **disque(90)})
    r = analyse.analyser()
    assert list(r["erreurs"]) == ["demarrage"]
    assert "Démarrage" in r["erreurs"]["demarrage"]
    assert r["bilan"]["scores"]["disque"] == 6  # le disque a quand même été évalué
    assert analyse.score_global(r) is None  # pas de score global trompeur
    rapport = analyse.rapport_texte(r)
    assert "Démarrage : erreur" in rapport and "Disque : 6 / 30" in rapport


def test_tous_les_modules_plantent(monkeypatch):
    faux_modules(monkeypatch, demarrage=plante, disque=plante, ressources=plante, batterie=plante)
    r = analyse.analyser()
    assert set(r["erreurs"]) == {"demarrage", "disque", "ressources", "batterie"}
    assert analyse.score_global(r) is None
    assert analyse.conseils(r) == []
    assert analyse.rapport_texte(r).count(": erreur") == 4


def test_batterie_hors_score(monkeypatch):
    faux_modules(monkeypatch, batterie=lambda: {"constats": ["Usure non mesurable sur ce PC."], **batterie(None)})
    r = analyse.analyser()
    assert analyse.points_module(r, "batterie") == "hors score"
    assert analyse.score_global(r) == 100


@pytest.mark.parametrize("note, niveau", [(100, "vert"), (80, "vert"), (79, "orange"),
                                          (50, "orange"), (49, "rouge"), (0, "rouge"), (None, "gris")])
def test_interpretation(note, niveau):
    assert analyse.interpretation(note)[0] == niveau


def test_rapport_avec_conseils(monkeypatch):
    faux_modules(monkeypatch, demarrage=lambda: {"constats": [], **demarrage(40)},
                 disque=lambda: {"constats": [], **disque(99)})
    rapport = analyse.rapport_texte(analyse.analyser())
    assert "Score : 40 / 100" in rapport
    assert "1. " in rapport and "Conseils :" in rapport


def test_journal_ecrit_dans_le_dossier(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)  # remis en place après le test
    fichier = journal.configurer(tmp_path)
    logging.getLogger("test").info("bonjour")
    logging.shutdown()
    assert fichier == tmp_path / "bilan.log"
    assert "bonjour" in fichier.read_text(encoding="utf-8")


def test_rapport_html_sans_nom_utilisateur(monkeypatch):
    maison = str(Path.home())
    programme = {"nom": "<script>alert(1)</script>", "chemin": maison + r"\AppData\outil.exe",
                 "editeur": None, "source": "Registre"}
    faux_modules(monkeypatch, demarrage=lambda: {"constats": [], "programmes": [programme] * 12},
                 disque=lambda: {"constats": [], **disque(90, [{"chemin": maison + r"\Downloads", "taille": 9 * GO}])},
                 ressources=plante)
    page = analyse.rapport_html(analyse.analyser())
    assert maison.lower() not in page.lower()  # ni le profil, ni le chemin du journal
    assert r"%USERPROFILE%\Downloads" in page and r"%USERPROFILE%\AppData\outil.exe" in page
    assert "<script>" not in page and "&lt;script&gt;" in page  # texte échappé
    assert "src=" not in page and "<link" not in page  # un seul fichier, sans ressource externe
    assert "Conseils" in page and "Mémoire et processeur : erreur" in page and "? / 100" in page


def test_arriere_plan_baisse_puis_retablit_la_priorite():
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentThread.restype = wintypes.HANDLE
    kernel32.GetThreadPriority.argtypes = [wintypes.HANDLE]
    priorite = lambda: kernel32.GetThreadPriority(kernel32.GetCurrentThread())
    avant = priorite()
    with analyse.arriere_plan():
        assert priorite() < avant
    assert priorite() == avant
