"""Tests du calcul du score. Lancer avec : python -m unittest"""

import os
import unittest

from modules import score

GO = 1024**3


def demarrage(nb: int) -> dict:
    return {"programmes": [{"nom": f"p{i}"} for i in range(nb)]}


def disque(pourcentage: float, gros_dossiers: list[dict] | None = None) -> dict:
    lecteur = os.environ.get("SystemDrive", "C:") + "\\"
    return {"disques": [{"disque": lecteur, "total": 100 * GO, "utilise": pourcentage * GO,
                         "libre": (100 - pourcentage) * GO, "pourcentage": pourcentage}],
            "gros_dossiers": gros_dossiers or []}


class TestBareme(unittest.TestCase):
    def test_disque(self):
        self.assertEqual(score.points_disque(50), 50)
        self.assertEqual(score.points_disque(70), 50)
        self.assertEqual(score.points_disque(82.5), 25)
        self.assertEqual(score.points_disque(95), 0)
        self.assertEqual(score.points_disque(100), 0)

    def test_demarrage(self):
        self.assertEqual(score.points_demarrage(0), 50)
        self.assertEqual(score.points_demarrage(10), 50)
        self.assertEqual(score.points_demarrage(11), 47)
        self.assertEqual(score.points_demarrage(22), 14)
        self.assertEqual(score.points_demarrage(40), 0)


class TestCalculer(unittest.TestCase):
    def test_pc_en_forme(self):
        resultat = score.calculer(demarrage(5), disque(40))
        self.assertEqual(resultat["score"], 100)
        self.assertEqual(resultat["scores"], {"demarrage": 50, "disque": 50})
        self.assertEqual(resultat["conseils"], [])

    def test_conseils_tries_par_impact(self):
        # Démarrage : -6 points ; disque à 90 % : -40 points -> le disque passe en premier.
        gros = [{"chemin": r"C:\Users\moi\AppData", "taille": 80 * GO},
                {"chemin": r"C:\Users\moi\Downloads", "taille": 30 * GO}]
        resultat = score.calculer(demarrage(12), disque(90, gros))
        self.assertEqual(resultat["score"], 44 + 10)
        conseils = resultat["conseils"]
        self.assertEqual(len(conseils), 3)
        self.assertIn("plein à 90 %", conseils[0])
        self.assertIn("Téléchargements", conseils[1])  # AppData n'est jamais proposé
        self.assertIn("12 programmes", conseils[2])

    def test_conseil_demarrage_prudent(self):
        conseil = score.calculer(demarrage(20), disque(40))["conseils"][0]
        self.assertIn("antivirus", conseil)
        self.assertIn("pilotes", conseil)

    def test_disque_systeme_absent(self):
        resultat = score.calculer(demarrage(0), {"disques": [], "gros_dossiers": []})
        self.assertEqual(resultat["scores"]["disque"], 50)


if __name__ == "__main__":
    unittest.main()
