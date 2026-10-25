"""Tests du module démarrage. Lancer avec : python -m unittest"""

import os
import struct
import tempfile
import unittest
import unittest.mock
import winreg
from pathlib import Path

from modules import demarrage


def faux_raccourci(chemin: str, unicode: bool) -> bytes:
    """Construit un .lnk minimal (en-tête + LinkInfo) pointant vers `chemin`."""
    entete = struct.pack("<I16sI", 0x4C, bytes(16), 0x02).ljust(0x4C, b"\0")
    if unicode:
        texte = chemin.encode("utf-16-le") + b"\0\0"
        decalages = struct.pack("<6I", 0x24, 1, 0, 0, 0, 0) + struct.pack("<2I", 0x24, 0x24 + len(texte) - 2)
    else:
        texte = chemin.encode("mbcs") + b"\0"
        decalages = struct.pack("<6I", 0x1C, 1, 0, 0x1C, 0, 0x1C + len(texte) - 1)
    corps = decalages + texte
    return entete + struct.pack("<I", 4 + len(corps)) + corps


class TestExtraireChemin(unittest.TestCase):
    def test_guillemets(self):
        self.assertEqual(demarrage.extraire_chemin(r'"C:\Program Files\App\app.exe" --cache'),
                         r"C:\Program Files\App\app.exe")

    def test_espaces_sans_guillemets(self):
        self.assertEqual(demarrage.extraire_chemin(r"C:\Program Files\App\app.EXE /min"),
                         r"C:\Program Files\App\app.EXE")

    def test_variable_environnement(self):
        attendu = os.path.expandvars(r"%WINDIR%\app.exe")
        self.assertEqual(demarrage.extraire_chemin(r"%WINDIR%\app.exe -x"), attendu)

    def test_exe_dans_le_path(self):
        self.assertTrue(os.path.isabs(demarrage.extraire_chemin("rundll32.exe shell32.dll,Truc")))


class TestRaccourci(unittest.TestCase):
    def test_ansi(self):
        self.assertEqual(demarrage.cible_raccourci(faux_raccourci(r"C:\App\app.exe", False)), r"C:\App\app.exe")

    def test_unicode(self):
        self.assertEqual(demarrage.cible_raccourci(faux_raccourci(r"C:\Éditions\app.exe", True)),
                         r"C:\Éditions\app.exe")

    def test_fichier_corrompu(self):
        self.assertIsNone(demarrage.cible_raccourci(b"pas un raccourci"))


class TestEditeur(unittest.TestCase):
    def test_fichier_windows(self):
        self.assertEqual(demarrage.editeur(os.path.expandvars(r"%WINDIR%\explorer.exe")), "Microsoft Corporation")

    def test_fichier_absent(self):
        self.assertIsNone(demarrage.editeur(r"C:\nexiste\pas.exe"))


class TestScan(unittest.TestCase):
    def test_structure(self):
        resultat = demarrage.scan()
        self.assertIn("score", resultat)
        self.assertEqual(len(resultat["constats"]), 1)
        for programme in resultat["programmes"]:
            self.assertEqual(set(programme), {"nom", "chemin", "editeur", "source", "actif"})
            self.assertTrue(programme["actif"])  # seuls les programmes actifs sont gardés

    def test_desactives_ignores(self):
        programmes = [{"nom": "Steam", "actif": True}, {"nom": "Epic", "actif": False},
                      {"nom": "Riot", "actif": False}]
        with unittest.mock.patch.object(demarrage, "lister_programmes", return_value=programmes):
            resultat = demarrage.scan()
        self.assertEqual([p["nom"] for p in resultat["programmes"]], ["Steam"])
        self.assertEqual(resultat["nb_desactives"], 2)
        self.assertEqual(resultat["constats"],
                         ["1 programme se lance au démarrage de Windows (2 autres désactivés dans les Paramètres)."])


class TestDossierDemarrage(unittest.TestCase):
    def test_raccourci_illisible(self):
        """Un raccourci illisible (accès refusé) ne fait pas échouer toute la partie Démarrage."""
        with tempfile.TemporaryDirectory() as dossier:
            Path(dossier, "Outil.lnk").write_bytes(faux_raccourci(r"C:\Outil\outil.exe", True))
            def refus(_chemin):
                raise PermissionError("Accès refusé")
            with (unittest.mock.patch.object(demarrage, "SOURCES_REGISTRE", []),
                  unittest.mock.patch.object(demarrage, "DOSSIERS_DEMARRAGE",
                                             [(dossier, "Dossier Démarrage", winreg.HKEY_CURRENT_USER)]),
                  unittest.mock.patch.object(Path, "read_bytes", refus)):
                programmes = demarrage.lister_programmes()
        self.assertEqual([(p["nom"], p["chemin"]) for p in programmes], [("Outil", str(Path(dossier, "Outil.lnk")))])


class TestDesactive(unittest.TestCase):
    def test_valeurs_startup_approved(self):
        self.assertFalse(demarrage.est_desactive(bytes([0x02]) + bytes(11)))  # activé
        self.assertFalse(demarrage.est_desactive(bytes([0x06]) + bytes(11)))
        self.assertTrue(demarrage.est_desactive(bytes([0x03]) + bytes(11)))  # désactivé par l'utilisateur
        self.assertTrue(demarrage.est_desactive(bytes([0x01]) + bytes(11)))
        self.assertFalse(demarrage.est_desactive(b""))  # valeur vide ou d'un autre type : on ne sait pas, actif
        self.assertFalse(demarrage.est_desactive(1))


if __name__ == "__main__":
    unittest.main()
