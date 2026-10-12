"""Tests du module disque. Lancer avec : python -m unittest"""

import tempfile
import unittest
from pathlib import Path

from modules import disque


def creer_fichier(chemin: Path, octets: int) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(b"x" * octets)


class TestTailleLisible(unittest.TestCase):
    def test_unites(self):
        self.assertEqual(disque.taille_lisible(500), "500 octets")
        self.assertEqual(disque.taille_lisible(1536), "1,5 Ko")
        self.assertEqual(disque.taille_lisible(3 * 1024**3), "3,0 Go")
        self.assertEqual(disque.taille_lisible(2 * 1024**4), "2,0 To")


class TestDossiers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.racine = Path(self.temp.name)
        creer_fichier(self.racine / "petit" / "a.txt", 10)
        creer_fichier(self.racine / "gros" / "b.txt", 300)
        creer_fichier(self.racine / "gros" / "sous" / "c.txt", 200)
        creer_fichier(self.racine / "moyen" / "d.txt", 100)
        creer_fichier(self.racine / "fichier_racine.txt", 9999)  # pas un dossier : ignoré

    def tearDown(self):
        self.temp.cleanup()

    def test_taille_recursive(self):
        self.assertEqual(disque.taille_dossier(str(self.racine / "gros")), 500)

    def test_dossier_absent(self):
        self.assertEqual(disque.taille_dossier(str(self.racine / "absent")), 0)

    def test_tri_et_limite(self):
        resultat = disque.gros_dossiers(self.racine, nombre=2)
        self.assertEqual([Path(d["chemin"]).name for d in resultat], ["gros", "moyen"])
        self.assertEqual([d["taille"] for d in resultat], [500, 100])


class TestDisques(unittest.TestCase):
    def test_structure(self):
        disques = disque.lister_disques()
        self.assertTrue(any(d["disque"].upper().startswith("C:") for d in disques))
        for d in disques:
            self.assertEqual(d["total"], d["utilise"] + d["libre"])


if __name__ == "__main__":
    unittest.main()
