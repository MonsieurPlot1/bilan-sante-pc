"""Garde-fous communs à tous les tests."""

import pytest

from modules import installation_pilotes, pilotes


@pytest.fixture(autouse=True)
def pilotes_hors_ligne(monkeypatch):
    """Aucun test ne lance PowerShell, n'interroge NVIDIA ni n'installe de pilote, même par une analyse complète
    lancée sans faux modules : remplacer ces fonctions explicitement dans le test qui en a besoin."""
    appels = []

    def interdit(*arguments, **_options):
        appels.append(arguments)
        raise AssertionError("un test a tenté d'utiliser PowerShell, le réseau ou d'installer des pilotes")
    for module, nom in ((pilotes, "_powershell"), (pilotes, "_ouvrir"), (installation_pilotes, "_ouvrir"),
                        (installation_pilotes, "_lancer_en_administrateur")):
        monkeypatch.setattr(module, nom, interdit)
    yield
    assert not appels, "un test a tenté d'utiliser PowerShell, le réseau ou d'installer des pilotes"
