"""Tests du module fichiers inutiles. Lancer avec : python -m pytest"""

import os

from modules import fichiers


def test_corbeille_reelle():
    toutes = fichiers.corbeille()
    systeme = fichiers.corbeille(os.environ.get("SystemDrive", "C:") + os.sep)
    assert 0 <= systeme <= toutes


def test_scan_reel():
    resultat = fichiers.scan()
    assert resultat["score"] is None  # hors score
    assert resultat["corbeille"] >= 0 and resultat["temporaires"] >= 0
    assert 0 <= resultat["recuperable_systeme"] <= resultat["corbeille"] + resultat["temporaires"]
    assert len(resultat["constats"]) == 2
