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
    tout = (resultat["corbeille"] + resultat["temporaires"] + sum(resultat["navigateurs"].values())
            + resultat["ancien_windows"])
    assert 0 <= resultat["recuperable_systeme"] <= tout
    assert len(resultat["constats"]) == 2 + bool(resultat["navigateurs"]) + bool(resultat["ancien_windows"])


def test_scan_sans_remesurer(monkeypatch):
    def interdit(*_):
        raise AssertionError("les fichiers temporaires ou les caches ont été remesurés")
    monkeypatch.setattr(fichiers, "taille_dossier", interdit)
    monkeypatch.setattr(fichiers, "caches_navigateurs", interdit)
    resultat = fichiers.scan({"temporaires": 1234, "navigateurs": {"Edge": 2048}, "ancien_windows": 4096})
    assert resultat["temporaires"] == 1234 and resultat["navigateurs"] == {"Edge": 2048}
    assert resultat["ancien_windows"] == 4096
    assert resultat["constats"][1:] == ["Fichiers temporaires : 1,2 Ko.",
                                       "Cache des navigateurs : 2,0 Ko (Edge 2,0 Ko).",
                                       "Ancienne version de Windows (Windows.old) : environ 4,0 Ko."]


def test_ancien_windows(monkeypatch):
    go = 1024 ** 3
    # Seul Windows.old pèse quelque chose : on vérifie qu'il est cherché sur le disque de Windows.
    monkeypatch.setattr(fichiers, "taille_dossier", lambda d: 20 * go if d.upper() == r"C:\WINDOWS.OLD" else 0)
    monkeypatch.setenv("SystemDrive", "c:")
    resultat = fichiers.scan()
    assert resultat["ancien_windows"] == 20 * go
    assert resultat["recuperable_systeme"] >= 20 * go  # compté dans la place récupérable
    assert "Ancienne version de Windows (Windows.old) : environ 20,0 Go." in resultat["constats"]


def test_caches_navigateurs(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    for dossier, octets in (("Google/Chrome/User Data/Default/Cache/Cache_Data", 1000),
                            ("Google/Chrome/User Data/Profile 1/Code Cache/js", 500),
                            ("Mozilla/Firefox/Profiles/abc.default/cache2/entries", 300),
                            ("Google/Chrome/User Data/Default/Bookmarks", 0)):  # pas un cache : ignoré
        (tmp_path / dossier).mkdir(parents=True)
        (tmp_path / dossier / "f").write_bytes(b"x" * octets)
    assert fichiers.caches_navigateurs() == {"Chrome": 1500, "Firefox": 300}  # Edge absent : pas listé
