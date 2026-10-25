"""Tests de l'historique des analyses. Lancer avec : python -m pytest"""

import json
from datetime import datetime, timedelta

import config
import historique

GO = 1024**3
NOMS = {"demarrage": "Démarrage", "disque": "Disque"}
DEBUT = datetime(2026, 10, 1, 9, 0)


def resultat(score: int | None, utilise: float = 50, jours: int = 0, version: int = config.SCORE_VERSION) -> dict:
    """Résultat d'analyse minimal ; score None = analyse incomplète."""
    scores = {"demarrage": 30, "disque": score - 30} if score is not None else {"demarrage": 30}
    disque = {"disques": [{"disque": "C:\\", "utilise": utilise * GO, "pourcentage": 50}],
              "gros_dossiers": [{"chemin": r"C:\Users\secret\Downloads", "taille": GO}]}
    return {"date": DEBUT + timedelta(days=jours), "modules": {"disque": disque},
            "bilan": {"score": score, "scores": scores, "version": version}}


def test_enregistre_seulement_des_chiffres(tmp_path):
    historique.enregistrer(resultat(70), tmp_path)
    contenu = historique.fichier(tmp_path).read_text(encoding="utf-8")
    assert "secret" not in contenu and "Downloads" not in contenu
    assert json.loads(contenu) == [{"date": "2026-10-01T09:00:00", "score_version": config.SCORE_VERSION,
                                    "score": 70, "scores": {"demarrage": 30, "disque": 40},
                                    "disque_utilise": 50 * GO}]


def test_analyse_incomplete_non_enregistree(tmp_path):
    assert historique.enregistrer(resultat(None), tmp_path) == []
    assert not historique.fichier(tmp_path).exists()


def test_comparaison(tmp_path):
    historique.enregistrer(resultat(67, utilise=53), tmp_path)
    entrees = historique.enregistrer(resultat(72, utilise=50, jours=1), tmp_path)
    assert historique.comparer(entrees, NOMS) == [
        "Score : 72 (+5)", "Démarrage : 30 (=)", "Disque : 42 (+5)", "Disque : 3,0 Go de moins utilisés",
        "(comparé à l'analyse du 01/10/2026 à 09:00)"]


def test_petite_difference_disque_ignoree(tmp_path):
    historique.enregistrer(resultat(70, utilise=50), tmp_path)
    entrees = historique.enregistrer(resultat(70, utilise=50.1, jours=1), tmp_path)
    assert not any("utilisés" in ligne for ligne in historique.comparer(entrees, NOMS))


def test_premiere_analyse(tmp_path):
    entrees = historique.enregistrer(resultat(70), tmp_path)
    assert "Première analyse" in historique.comparer(entrees, NOMS)[0]


def test_versions_differentes_pas_comparees(tmp_path):
    historique.enregistrer(resultat(90, version=1), tmp_path)
    entrees = historique.enregistrer(resultat(60, jours=1), tmp_path)
    assert historique.comparer(entrees, NOMS) == ["Nouvelle version du calcul, pas de comparaison possible."]
    assert [e["score"] for e in historique.serie(entrees)] == [60]  # la v1 n'est pas dans le graphique


def test_evolution_du_disque_sur_le_mois(tmp_path):
    historique.enregistrer(resultat(70, utilise=40, jours=0), tmp_path)  # plus d'un mois avant : ignorée
    historique.enregistrer(resultat(70, utilise=50, jours=10), tmp_path)  # référence : la plus ancienne du mois
    historique.enregistrer(resultat(70, utilise=60, jours=20), tmp_path)
    entrees = historique.enregistrer(resultat(70, utilise=62, jours=35), tmp_path)
    lignes = historique.comparer(entrees, NOMS)
    assert lignes[-2].startswith("(comparé à l'analyse du 21/10/2026")
    assert lignes[-1] == "Depuis le 11/10 : 12,0 Go de plus utilisés sur le disque de Windows"


def test_pas_d_evolution_sans_assez_de_recul(tmp_path):
    historique.enregistrer(resultat(70, utilise=40), tmp_path)
    entrees = historique.enregistrer(resultat(70, utilise=50, jours=6), tmp_path)  # moins d'une semaine
    assert historique.tendance_disque(entrees) is None
    assert historique.tendance_disque([]) is None


def test_evolution_meme_apres_changement_de_calcul(tmp_path):
    historique.enregistrer(resultat(90, utilise=55, version=1), tmp_path)
    entrees = historique.enregistrer(resultat(60, utilise=50, jours=8), tmp_path)
    assert historique.comparer(entrees, NOMS) == ["Nouvelle version du calcul, pas de comparaison possible.",
                                                  "Depuis le 01/10 : 5,0 Go de moins utilisés sur le disque de Windows"]


def test_serie_limitee_a_20(tmp_path):
    for jour in range(25):
        historique.enregistrer(resultat(50 + jour, jours=jour), tmp_path)
    scores = [e["score"] for e in historique.serie(historique.charger(tmp_path))]
    assert scores == list(range(55, 75))


def test_effacer(tmp_path):
    historique.enregistrer(resultat(70), tmp_path)
    historique.effacer(tmp_path)
    assert historique.charger(tmp_path) == []
    historique.effacer(tmp_path)  # déjà effacé : pas d'erreur


def test_fichier_abime_mis_de_cote(tmp_path):
    historique.fichier(tmp_path).write_text("{pas du json", encoding="utf-8")
    assert historique.charger(tmp_path) == []
    assert (tmp_path / "historique.abime.json").exists()
    assert historique.enregistrer(resultat(70), tmp_path)[0]["score"] == 70


def test_entrees_abimees_ecartees(tmp_path):
    """Une entrée abîmée (modifiée à la main…) ferait planter le graphique : seules les bonnes sont gardées."""
    bonne = historique.entree(resultat(70))
    abimees = [{"date": "hier", "score": 50, "scores": {}}, {"date": bonne["date"], "score": "70", "scores": {}},
               {"date": bonne["date"], "score": 70}, "texte", None]
    historique.fichier(tmp_path).write_text(json.dumps([*abimees, bonne]), encoding="utf-8")
    assert historique.charger(tmp_path) == [bonne]
