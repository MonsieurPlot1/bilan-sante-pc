"""Tests du calcul du score (v4). Lancer avec : python -m pytest"""

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


def fichiers(corbeille: float = 0, temporaires: float = 0) -> dict:
    """Tailles en Go, toutes sur le disque de Windows."""
    return {"corbeille": corbeille * GO, "temporaires": temporaires * GO,
            "recuperable_systeme": (corbeille + temporaires) * GO}


def redemarrage(jours: float = 1, en_attente: bool = False) -> dict:
    return {"jours": jours, "en_attente": en_attente}


def alimentation(mode: int | None = 2, plan_economies: bool = False) -> dict:
    """Mode 2 : équilibré."""
    return {"mode": mode, "plan_economies": plan_economies}


def batterie(sante: float | None = 0.9) -> dict:
    return {"applicable": True, "niveau": 80, "branche": True, "sante": sante}


def pc(**modules) -> dict:
    """Résultats d'un PC en forme, sans batterie, où l'on remplace certains modules."""
    return {"demarrage": demarrage(5), "disque": disque(40), "ressources": ressources(),
            "redemarrage": redemarrage()} | modules


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
        self.assertEqual(resultat["score"], 25 + 25 + 20 + 15 + 4)
        self.assertIn("50 % de sa capacité", resultat["conseils"][0])


class TestRedemarrage(unittest.TestCase):
    def test_seuils(self):
        points = lambda jours: score.calculer(pc(redemarrage=redemarrage(jours)))["scores"]["redemarrage"]
        self.assertEqual(points(7), 15)
        self.assertEqual(points(18.5), 8)  # à mi-chemin entre 7 et 30 jours : 7,5 arrondi
        self.assertEqual(points(30), 0)

    def test_mise_a_jour_en_attente(self):
        resultat = score.calculer(pc(redemarrage=redemarrage(1, en_attente=True)))
        self.assertEqual(resultat["scores"]["redemarrage"], 8)  # plafonné à la moitié des 15 points
        conseil = resultat["conseils"][0]
        self.assertIn("mise à jour", conseil)
        self.assertIn("Redémarrer", conseil)
        self.assertNotIn("n'a pas redémarré depuis", conseil)  # redémarré hier : on n'en parle pas

    def test_longtemps_sans_redemarrer(self):
        conseil = score.calculer(pc(redemarrage=redemarrage(20)))["conseils"][0]
        self.assertIn("depuis 20 jours", conseil)
        self.assertIn("« Arrêter » ne suffit pas", conseil)
        self.assertNotIn("mise à jour", conseil)


class TestFichiers(unittest.TestCase):
    def test_hors_score(self):
        resultat = score.calculer(pc(fichiers=fichiers(50, 5)))
        self.assertEqual(resultat["score"], 100)
        self.assertNotIn("fichiers", resultat["scores"])
        self.assertEqual(resultat["conseils"], [])  # disque à 40 % : rien à gagner, pas de conseil

    def test_conseil_quand_le_disque_est_plein(self):
        # Disque à 90 % de 100 Go : libérer 10 Go le ramène à 80 % -> 30 x (0,6 - 0,2) = 12 points regagnés.
        resultat = score.calculer(pc(disque=disque(90), fichiers=fichiers(8, 2)))
        conseil = resultat["conseils"][1]  # après le conseil disque (24 points)
        self.assertTrue(conseil.startswith("La Corbeille contient 8,0 Go et les fichiers temporaires occupent 2,0 Go"))
        self.assertIn("rien d'important", conseil)  # prudence : vider la Corbeille est définitif

    def test_corbeille_vide(self):
        conseil = score.calculer(pc(disque=disque(90), fichiers=fichiers(0, 10)))["conseils"][1]
        self.assertTrue(conseil.startswith("Les fichiers temporaires occupent 10,0 Go"))

    def test_trop_peu_pour_un_conseil(self):
        # 100 Mo sur 100 Go : moins d'un point à regagner.
        resultat = score.calculer(pc(disque=disque(90), fichiers=fichiers(0, 0.1)))
        self.assertEqual(len(resultat["conseils"]), 1)


class TestAlimentation(unittest.TestCase):
    def test_hors_score_et_sans_conseil_si_equilibre(self):
        resultat = score.calculer(pc(alimentation=alimentation(2)))
        self.assertEqual(resultat["score"], 100)
        self.assertNotIn("alimentation", resultat["scores"])
        self.assertEqual(resultat["conseils"], [])

    def test_mode_illisible(self):
        self.assertEqual(score.calculer(pc(alimentation=alimentation(None)))["conseils"], [])

    def test_economiseur(self):
        resultat = score.calculer(pc(alimentation=alimentation(0)))
        self.assertEqual(resultat["score"], 100)  # hors score : le conseil n'enlève aucun point
        self.assertIn("L'économiseur d'énergie est activé", resultat["conseils"][0])
        self.assertIn("utile sur batterie", resultat["conseils"][0])  # pas un réglage à couper à tout prix

    def test_plan_economies(self):
        conseil = score.calculer(pc(alimentation=alimentation(2, plan_economies=True)))["conseils"][0]
        self.assertIn("« Utilisation normale »", conseil)

    def test_efficacite(self):
        conseil = score.calculer(pc(alimentation=alimentation(1)))["conseils"][0]
        self.assertIn("choisis « Équilibré »", conseil)

    def test_economiseur_avant_le_plan(self):
        conseils = score.calculer(pc(alimentation=alimentation(0, plan_economies=True)))["conseils"]
        self.assertEqual(len(conseils), 1)
        self.assertIn("économiseur", conseils[0])

    def test_place_parmi_les_conseils(self):
        # Disque à 90 % : 24 points à regagner, avant l'alimentation (10).
        conseils = score.calculer(pc(disque=disque(90), alimentation=alimentation(1)))["conseils"]
        self.assertIn("Ton disque", conseils[0])
        self.assertIn("efficacité énergétique", conseils[1])


class TestCasExtremes(unittest.TestCase):
    def test_ram_a_95(self):
        resultat = score.calculer(pc(ressources=ressources(ram=95)))
        self.assertEqual(resultat["scores"]["ressources"], 12)  # RAM à 0, processeur au maximum : 12,5 arrondi
        self.assertEqual(resultat["score"], 30 + 30 + 12 + 15)
        conseil = resultat["conseils"][0]
        self.assertIn("95 %", conseil)
        self.assertIn("chrome (3,0 Go)", conseil)
        self.assertIn("antivirus", conseil)  # prudence : certains programmes doivent rester ouverts

    def test_ram_pleine_sans_processus_lisible(self):
        conseil = score.calculer(pc(ressources=ressources(ram=95, processus=[])))["conseils"][0]
        self.assertNotIn("Ceux qui en prennent le plus", conseil)

    def test_processeur_occupe(self):
        resultat = score.calculer(pc(ressources=ressources(cpu=100)))
        self.assertEqual(resultat["scores"]["ressources"], 12)
        self.assertIn("Gestionnaire des tâches", resultat["conseils"][0])

    def test_disque_plein_a_99(self):
        resultat = score.calculer(pc(disque=disque(99)))
        self.assertEqual(resultat["scores"]["disque"], 0)
        self.assertEqual(resultat["score"], 70)
        self.assertIn("plein à 99 %", resultat["conseils"][0])

    def test_40_programmes(self):
        resultat = score.calculer(pc(demarrage=demarrage(40)))
        self.assertEqual(resultat["scores"]["demarrage"], 0)  # plancher : jamais négatif
        self.assertIn("40 programmes", resultat["conseils"][0])

    def test_tout_au_pire(self):
        gros = [{"chemin": r"C:\Users\moi\Videos", "taille": 200 * GO}]
        resultat = score.calculer({"demarrage": demarrage(40), "disque": disque(99, gros),
                                   "ressources": ressources(ram=99, cpu=100), "redemarrage": redemarrage(40, True),
                                   "batterie": batterie(0.3)})
        self.assertEqual(resultat["score"], 0)
        self.assertEqual(len(resultat["conseils"]), config.NB_CONSEILS_MAX)

    def test_aucune_donnee(self):
        resultat = score.calculer({"demarrage": {"programmes": []}, "disque": {"disques": [], "gros_dossiers": []},
                                   "ressources": ressources(ram=0, cpu=0, processus=[]),
                                   "redemarrage": redemarrage(0)})
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
        self.assertEqual(resultat["scores"], {"demarrage": 0, "ressources": 25, "redemarrage": 15})
        self.assertIn("40 programmes", resultat["conseils"][0])

    def test_module_manquant(self):
        self.assertIsNone(score.calculer({})["score"])


class TestConseils(unittest.TestCase):
    def test_tries_par_impact(self):
        # Démarrage : -3,5 points ; disque à 90 % : -24 points -> le disque passe en premier.
        gros = [{"chemin": r"C:\Users\moi\AppData", "taille": 80 * GO},
                {"chemin": r"C:\Users\moi\Downloads", "taille": 30 * GO}]
        resultat = score.calculer(pc(demarrage=demarrage(12), disque=disque(90, gros)))
        self.assertEqual(resultat["score"], 26 + 6 + 25 + 15)
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
        self.assertEqual(resultat["scores"]["disque"], 30)


if __name__ == "__main__":
    unittest.main()
