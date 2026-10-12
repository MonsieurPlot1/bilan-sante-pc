"""Tests du calcul du score (v2). Lancer avec : python -m pytest"""

import os
import unittest

import config
from modules import score

GO = 1024**3


def demarrage(nb: int) -> dict:
    return {"programmes": [{"nom": f"p{i}", "editeur": None, "chemin": rf"C:\p{i}.exe", "source": "Registre"}
                           for i in range(nb)]}


def disque(pourcentage: float, gros_dossiers: list[dict] | None = None) -> dict:
    lecteur = os.environ.get("SystemDrive", "C:") + "\\"
    return {"disques": [{"disque": lecteur, "total": 100 * GO, "utilise": pourcentage * GO,
                         "libre": (100 - pourcentage) * GO, "pourcentage": pourcentage}],
            "gros_dossiers": gros_dossiers or []}


def ressources(ram: float = 40, cpu: float = 10, processus: list[dict] | None = None) -> dict:
    if processus is None:
        processus = [{"nom": "chrome.exe", "octets": 3 * GO}, {"nom": "Code.exe", "octets": 2 * GO}]
    return {"ram": {"total": 16 * GO, "utilise": 16 * GO * ram / 100, "pourcentage": ram}, "cpu": cpu,
            "processus": processus}


def batterie(sante: float | None = 0.9) -> dict:
    return {"applicable": True, "niveau": 80, "branche": True, "sante": sante}


def pc(**modules) -> dict:
    """Résultats d'un PC en forme, sans batterie, où l'on remplace certains modules."""
    return {"demarrage": demarrage(5), "disque": disque(40), "ressources": ressources()} | modules


class TestBareme(unittest.TestCase):
    def test_lineaire(self):
        self.assertEqual(score.lineaire(50, 70, 95), 1)
        self.assertEqual(score.lineaire(70, 70, 95), 1)
        self.assertEqual(score.lineaire(82.5, 70, 95), 0.5)
        self.assertEqual(score.lineaire(95, 70, 95), 0)
        self.assertEqual(score.lineaire(100, 70, 95), 0)

    def test_total_100(self):
        self.assertEqual(sum(config.POINTS_AVEC_BATTERIE.values()), 100)
        self.assertEqual(sum(config.POINTS_SANS_BATTERIE.values()), 100)

    def test_version(self):
        self.assertEqual(score.calculer(pc())["version"], config.SCORE_VERSION)


class TestBatterie(unittest.TestCase):
    def test_pas_de_batterie(self):
        resultat = score.calculer(pc())
        self.assertEqual(resultat["bareme"], config.POINTS_SANS_BATTERIE)
        self.assertEqual(resultat["score"], 100)
        self.assertNotIn("batterie", resultat["scores"])

    def test_batterie_non_applicable(self):
        resultat = score.calculer(pc(batterie={"applicable": False}))
        self.assertEqual(resultat["bareme"], config.POINTS_SANS_BATTERIE)
        self.assertEqual(resultat["score"], 100)

    def test_batterie_saine(self):
        resultat = score.calculer(pc(batterie=batterie(0.9)))
        self.assertEqual(resultat["bareme"], config.POINTS_AVEC_BATTERIE)
        self.assertEqual(resultat["score"], 100)

    def test_usure_non_mesurable_hors_score(self):
        resultat = score.calculer(pc(batterie=batterie(None)))
        self.assertEqual(resultat["bareme"], config.POINTS_SANS_BATTERIE)
        self.assertEqual(resultat["score"], 100)

    def test_batterie_usee(self):
        # Usure 50 % : entre 20 et 60 % -> 1/4 des 15 points (3,75 arrondi à 4).
        resultat = score.calculer(pc(batterie=batterie(0.5)))
        self.assertEqual(resultat["scores"]["batterie"], 4)
        self.assertEqual(resultat["score"], 30 + 30 + 25 + 4)
        self.assertIn("50 % de sa capacité", resultat["conseils"][0])


class TestCasExtremes(unittest.TestCase):
    def test_ram_a_95(self):
        resultat = score.calculer(pc(ressources=ressources(ram=95)))
        self.assertEqual(resultat["scores"]["ressources"], 15)  # RAM à 0, processeur au maximum
        self.assertEqual(resultat["score"], 35 + 35 + 15)
        conseil = resultat["conseils"][0]
        self.assertIn("95 %", conseil)
        self.assertIn("chrome (3,0 Go)", conseil)
        self.assertIn("antivirus", conseil)  # prudence : certains programmes doivent rester ouverts

    def test_ram_pleine_sans_processus_lisible(self):
        conseil = score.calculer(pc(ressources=ressources(ram=95, processus=[])))["conseils"][0]
        self.assertNotIn("Ceux qui en prennent le plus", conseil)

    def test_processeur_occupe(self):
        resultat = score.calculer(pc(ressources=ressources(cpu=100)))
        self.assertEqual(resultat["scores"]["ressources"], 15)
        self.assertIn("Gestionnaire des tâches", resultat["conseils"][0])

    def test_disque_plein_a_99(self):
        resultat = score.calculer(pc(disque=disque(99)))
        self.assertEqual(resultat["scores"]["disque"], 0)
        self.assertEqual(resultat["score"], 65)
        self.assertIn("plein à 99 %", resultat["conseils"][0])

    def test_40_programmes(self):
        resultat = score.calculer(pc(demarrage=demarrage(40)))
        self.assertEqual(resultat["scores"]["demarrage"], 0)  # plancher : jamais négatif
        self.assertIn("40 programmes", resultat["conseils"][0])

    def test_tout_au_pire(self):
        gros = [{"chemin": r"C:\Users\moi\Videos", "taille": 200 * GO}]
        resultat = score.calculer({"demarrage": demarrage(40), "disque": disque(99, gros),
                                   "ressources": ressources(ram=99, cpu=100), "batterie": batterie(0.3)})
        self.assertEqual(resultat["score"], 0)
        self.assertEqual(len(resultat["conseils"]), config.NB_CONSEILS_MAX)

    def test_aucune_donnee(self):
        resultat = score.calculer({"demarrage": {"programmes": []}, "disque": {"disques": [], "gros_dossiers": []},
                                   "ressources": ressources(ram=0, cpu=0, processus=[])})
        self.assertEqual(resultat["score"], 100)
        self.assertEqual(resultat["conseils"], [])

    def test_tous_modules_en_erreur(self):
        resultat = score.calculer({"demarrage": None, "disque": None, "ressources": None, "batterie": None})
        self.assertIsNone(resultat["score"])
        self.assertEqual(resultat["scores"], {})
        self.assertEqual(resultat["conseils"], [])

    def test_un_module_en_erreur(self):
        resultat = score.calculer(pc(disque=None, demarrage=demarrage(40)))
        self.assertIsNone(resultat["score"])  # score global trompeur sans le disque
        self.assertEqual(resultat["scores"], {"demarrage": 0, "ressources": 30})
        self.assertIn("40 programmes", resultat["conseils"][0])

    def test_module_manquant(self):
        self.assertIsNone(score.calculer({})["score"])


class TestConseils(unittest.TestCase):
    def test_tries_par_impact(self):
        # Démarrage : -4 points ; disque à 90 % : -28 points -> le disque passe en premier.
        gros = [{"chemin": r"C:\Users\moi\AppData", "taille": 80 * GO},
                {"chemin": r"C:\Users\moi\Downloads", "taille": 30 * GO}]
        resultat = score.calculer(pc(demarrage=demarrage(12), disque=disque(90, gros)))
        self.assertEqual(resultat["score"], 31 + 7 + 30)
        conseils = resultat["conseils"]
        self.assertEqual(len(conseils), 3)
        self.assertIn("plein à 90 %", conseils[0])
        self.assertIn("Téléchargements", conseils[1])  # AppData n'est jamais proposé
        self.assertIn("12 programmes", conseils[2])

    def test_demarrage_prudent(self):
        conseil = score.calculer(pc(demarrage=demarrage(20)))["conseils"][0]
        self.assertIn("antivirus", conseil)
        self.assertIn("pilotes", conseil)

    def test_gros_dossier_sous_le_seuil(self):
        petit = [{"chemin": r"C:\Users\moi\Downloads", "taille": 4 * GO}]
        conseils = score.calculer(pc(disque=disque(90, petit)))["conseils"]
        self.assertEqual(len(conseils), 1)  # seul le conseil disque, pas celui du dossier

    def test_petite_perte_sans_conseil(self):
        # RAM à 71 % : moins d'un point perdu, pas de quoi déranger avec un conseil.
        resultat = score.calculer(pc(ressources=ressources(ram=71)))
        self.assertEqual(resultat["conseils"], [])

    def test_disque_systeme_absent(self):
        resultat = score.calculer(pc(disque={"disques": [], "gros_dossiers": []}))
        self.assertEqual(resultat["scores"]["disque"], 35)


if __name__ == "__main__":
    unittest.main()
