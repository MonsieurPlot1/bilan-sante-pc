"""Tests du module jeux et affichage. Lancer avec : python -m pytest"""

from datetime import date

from modules import jeux

ENTRELACE = jeux.ENTRELACE


def test_frequence_maximale_a_la_resolution_actuelle():
    modes = [(1920, 1080, 60, 0), (1920, 1080, 144, 0), (1280, 720, 240, 0), (1920, 1080, 165, ENTRELACE)]
    assert jeux.frequence_maximale(modes, 1920, 1080) == 144  # ni une autre résolution, ni un mode entrelacé
    assert jeux.frequence_maximale(modes, 1080, 1920) == 144  # écran tourné d'un quart de tour
    assert jeux.frequence_maximale(modes, 2560, 1440) == 0  # résolution inconnue de la liste


def test_date_du_pilote():
    assert jeux.date_pilote("9-17-2026") == date(2026, 9, 17)  # mois en premier
    assert jeux.date_pilote("17-9-2026") is None and jeux.date_pilote(None) is None


def test_carte_des_jeux():
    integree = {"nom": "AMD Radeon(TM) Graphics", "memoire": 512 * 1024**2}
    separee = {"nom": "NVIDIA GeForce RTX 3060 Laptop GPU", "memoire": 6 * 1024**3}
    assert jeux.carte_des_jeux([integree, separee]) is separee  # PC portable à deux cartes
    assert jeux.carte_des_jeux([]) is None


def test_constats():
    ecran = {"principal": True, "largeur": 1920, "hauteur": 1080, "frequence": 60, "maximum": 144}
    integree = {"nom": "AMD Radeon(TM) Graphics", "date": date(2022, 9, 28), "memoire": 1}
    separee = {"nom": "NVIDIA GeForce RTX 3060", "date": date(2026, 9, 17), "memoire": 2}
    assert jeux.constats([ecran], [integree, separee], separee, False) == [
        "Écran : 60 Hz en 1920 × 1080, alors qu'il peut aller jusqu'à 144 Hz.",
        "Carte graphique pour les jeux : NVIDIA GeForce RTX 3060, pilote du 17/09/2026.",
        "Autre carte graphique : AMD Radeon(TM) Graphics, pilote du 28/09/2022.",
        "Mode jeu de Windows : désactivé."]
    assert jeux.constats([], [], None, True) == ["Fréquence de l'écran non lisible sur ce PC.",
                                                 "Carte graphique non reconnue.", "Mode jeu de Windows : activé."]


def test_scan_reel():
    resultat = jeux.scan()
    assert resultat["score"] is None  # hors score
    assert isinstance(resultat["mode_jeu"], bool) and isinstance(resultat["sur_batterie"], bool)
    for ecran in resultat["ecrans"]:
        assert 1 < ecran["frequence"] <= ecran["maximum"]
    for carte in resultat["cartes"]:
        assert carte["fabricant"] in ("NVIDIA", "AMD", "Intel")
    assert resultat["constats"][-1].startswith("Mode jeu de Windows")
