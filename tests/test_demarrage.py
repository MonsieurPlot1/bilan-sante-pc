"""Tests du module démarrage. Lancer avec : python -m unittest"""

import os
import struct
import unittest

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
            self.assertEqual(set(programme), {"nom", "chemin", "editeur", "source"})


if __name__ == "__main__":
    unittest.main()
