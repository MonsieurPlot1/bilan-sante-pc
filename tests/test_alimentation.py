"""Tests du module alimentation. Lancer avec : python -m pytest"""

from modules import alimentation


def test_scan_reel():
    resultat = alimentation.scan()
    assert resultat["score"] is None  # hors score
    assert resultat["mode"] is None or resultat["mode"] in alimentation.MODES
    assert isinstance(resultat["plan_economies"], bool)
    assert resultat["constats"][0].startswith("Mode d'alimentation")


def test_constats(monkeypatch):
    monkeypatch.setattr(alimentation, "mode_effectif", lambda: alimentation.EFFICACITE)
    monkeypatch.setattr(alimentation, "plan_economies", lambda: True)
    assert alimentation.scan()["constats"] == ["Mode d'alimentation : meilleure efficacité énergétique.",
                                               "Mode de gestion de l'alimentation : Économies d'énergie."]


def test_mode_illisible(monkeypatch):
    monkeypatch.setattr(alimentation, "mode_effectif", lambda: None)
    monkeypatch.setattr(alimentation, "plan_economies", lambda: False)
    assert alimentation.scan()["constats"] == ["Mode d'alimentation non lisible sur ce PC."]
