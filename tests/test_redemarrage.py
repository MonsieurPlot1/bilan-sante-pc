"""Tests du module redémarrage. Lancer avec : python -m pytest"""

from modules import redemarrage


def test_duree_lisible():
    assert redemarrage.duree_lisible(0.4) == "moins d'un jour"
    assert redemarrage.duree_lisible(1.9) == "1 jour"
    assert redemarrage.duree_lisible(12.2) == "12 jours"


def test_cle_existe():
    assert redemarrage.cle_existe(r"SOFTWARE\Microsoft\Windows\CurrentVersion")
    assert not redemarrage.cle_existe(r"SOFTWARE\Cle\Qui\N\Existe\Pas")


def test_scan_reel():
    resultat = redemarrage.scan()
    assert resultat["jours"] >= 0
    assert isinstance(resultat["en_attente"], bool)
    assert resultat["constats"][0].startswith("Dernier redémarrage complet : il y a ")
    assert len(resultat["constats"]) == (2 if resultat["en_attente"] else 1)
