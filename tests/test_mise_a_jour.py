"""Tests des mises à jour, sans réseau et sans toucher à l'application installée. Lancer avec : python -m pytest"""

import hashlib
import io
import json
import os
import re
import sys
from pathlib import Path

import pytest

from modules import mise_a_jour


@pytest.fixture(autouse=True)
def reseau_et_lancement_interdits(monkeypatch):
    """Aucun test n'utilise le réseau ni ne lance l'application : remplacer _ouvrir et _lancer explicitement."""
    def interdit(*_):
        raise AssertionError("un test a tenté d'utiliser le réseau ou de lancer l'application")
    monkeypatch.setattr(mise_a_jour, "_ouvrir", interdit)
    monkeypatch.setattr(mise_a_jour, "_lancer", interdit)
    monkeypatch.setattr(mise_a_jour, "PAUSE", 0)


def fichier_joint(tag: str, nom: str) -> dict:
    """Un fichier joint à une version publiée, avec son empreinte."""
    return {"name": nom, "size": 10, "digest": "sha256:" + "AB" * 32,
            "browser_download_url": f"{mise_a_jour.ORIGINE}{tag}/{nom}"}


def version(tag: str, brouillon: bool = False, avec_installateur: bool = True, notes: str = "- Nouveauté") -> dict:
    """Une version publiée, telle que la liste de GitHub la décrit (zip de la v0.4.1 et d'avant à côté)."""
    fichiers = [fichier_joint(tag, f"BilanSantePC-{tag}-windows.zip")]
    if avec_installateur:
        fichiers.append(fichier_joint(tag, f"BilanSantePC-Installation-{tag}.exe"))
    return {"tag_name": tag, "draft": brouillon, "prerelease": True, "body": notes, "assets": fichiers,
            "html_url": f"https://github.com/{mise_a_jour.DEPOT}/releases/tag/{tag}"}


def servir(contenu: bytes):
    """Remplace la réponse de GitHub par `contenu`."""
    return lambda _url: io.BytesIO(contenu)


def fichier_publie(contenu: bytes, **valeurs) -> dict:
    return {"nom": "BilanSantePC-Installation-v0.9.0.exe", "taille": len(contenu),
            "url": f"{mise_a_jour.ORIGINE}v0.9.0/BilanSantePC-Installation-v0.9.0.exe",
            "empreinte": hashlib.sha256(contenu).hexdigest()} | valeurs


def application(dossier: Path, exe: bytes, interne: dict[str, bytes]) -> Path:
    """Un dossier d'application : le .exe et son dossier _internal."""
    (dossier / "_internal").mkdir(parents=True)
    (dossier / mise_a_jour.NOM_EXE).write_bytes(exe)
    for nom, contenu in interne.items():
        (dossier / "_internal" / nom).write_bytes(contenu)
    return dossier


@pytest.mark.parametrize("texte, attendu", [("v0.3.8", (0, 3, 8)), ("0.3.6.1", (0, 3, 6, 1)), ("v1.0.0-beta", None),
                                            ("", None), ("v0.3.x", None), ("v0.\u0663.8", None)])
def test_numero(texte, attendu):
    assert mise_a_jour.numero(texte) == attendu


def test_la_plus_recente_des_versions_publiees():
    versions = [version("v0.3.8"), version("v0.3.10", notes="- Dix"), version("v0.3.9"),
                version("v0.4.0", brouillon=True), {"tag_name": "essai"}, {"tag_name": None}]
    nouvelle = mise_a_jour.plus_recente(versions, "0.3.8")
    assert nouvelle["version"] == "0.3.10"  # 10 > 9 : comparaison des nombres, pas du texte ; brouillon écarté
    assert nouvelle["notes"] == "- Dix"
    assert nouvelle["page"].endswith("/releases/tag/v0.3.10")
    assert nouvelle["installateur"]["url"].endswith("/v0.3.10/BilanSantePC-Installation-v0.3.10.exe")


@pytest.mark.parametrize("actuelle, publiees, attendu", [
    ("0.3.8", ["v0.3.8", "v0.3.7"], None),
    ("0.3.6.1", ["v0.3.6"], None),
    ("0.3.6", ["v0.3.6.1"], "0.3.6.1"),
    ("0.3.8", [], None),
])
def test_deja_a_jour_ou_pas(actuelle, publiees, attendu):
    nouvelle = mise_a_jour.plus_recente([version(tag) for tag in publiees], actuelle)
    assert (nouvelle and nouvelle["version"]) == attendu


def test_installateur_de_la_version():
    assert mise_a_jour.installateur_de(version("v0.9.0")) == {
        "nom": "BilanSantePC-Installation-v0.9.0.exe", "taille": 10, "empreinte": "ab" * 32,
        "url": f"{mise_a_jour.ORIGINE}v0.9.0/BilanSantePC-Installation-v0.9.0.exe"}
    assert mise_a_jour.installateur_de(version("v0.4.1", avec_installateur=False)) is None  # le zip seul ne sert pas
    sans_empreinte = version("v0.9.0")
    sans_empreinte["assets"][1]["digest"] = None
    assert mise_a_jour.installateur_de(sans_empreinte) is None  # sans empreinte, pas d'installation automatique
    ailleurs = version("v0.9.0")
    ailleurs["assets"][1]["browser_download_url"] = "https://exemple.com/BilanSantePC-Installation-v0.9.0.exe"
    assert mise_a_jour.installateur_de(ailleurs) is None


def test_notes_lisibles():
    notes = ("- Mode clair revu : fond plus lumineux,\n  cartes d'un blanc net.\n- Nouvel onglet.\n")
    assert mise_a_jour.notes_lisibles(notes) == "• Mode clair revu : fond plus lumineux, cartes d'un blanc net.\n" \
                                                "• Nouvel onglet."
    longues = mise_a_jour.notes_lisibles("- " + "mot " * 300, 100)
    assert len(longues) <= 101 and longues.endswith("…")
    assert mise_a_jour.notes_lisibles("") == ""


def test_chercher(monkeypatch):
    monkeypatch.setattr(mise_a_jour, "_ouvrir", servir(json.dumps([version("v99.0.0")]).encode()))
    assert mise_a_jour.chercher()["version"] == "99.0.0"


@pytest.mark.parametrize("reponse", [OSError("hors ligne"), b"pas du json", b'{"message": "API rate limit exceeded"}'])
def test_chercher_sans_reponse_utile(monkeypatch, reponse):
    def ouvrir(_url):
        if isinstance(reponse, Exception):
            raise reponse
        return io.BytesIO(reponse)
    monkeypatch.setattr(mise_a_jour, "_ouvrir", ouvrir)
    assert mise_a_jour.chercher() is None  # rien à signaler, pas de plantage


def test_telecharger_verifie_le_fichier(monkeypatch, tmp_path):
    donnees = os.urandom(600 * 1024)
    monkeypatch.setattr(mise_a_jour, "_ouvrir", servir(donnees))
    parts = []
    chemin = mise_a_jour.telecharger(fichier_publie(donnees), tmp_path, parts.append, lambda: False)
    assert chemin.read_bytes() == donnees
    assert parts[-1] == 1.0 and parts == sorted(parts)


@pytest.mark.parametrize("valeurs", [{"empreinte": "00" * 32}, {"taille": 1000}, {"taille": 1000 * 1024}])
def test_telecharger_refuse_un_fichier_different(monkeypatch, tmp_path, valeurs):
    donnees = os.urandom(600 * 1024)
    monkeypatch.setattr(mise_a_jour, "_ouvrir", servir(donnees))
    with pytest.raises(mise_a_jour.Invalide):
        mise_a_jour.telecharger(fichier_publie(donnees, **valeurs), tmp_path, lambda _part: None, lambda: False)


def test_telecharger_seulement_depuis_github(tmp_path):
    autre = fichier_publie(b"x", url="https://exemple.com/BilanSantePC-v0.9.0-windows.zip")
    with pytest.raises(mise_a_jour.Invalide):  # et _ouvrir n'est jamais appelé (fixture)
        mise_a_jour.telecharger(autre, tmp_path, lambda _part: None, lambda: False)


def test_telecharger_arrete(monkeypatch, tmp_path):
    donnees = os.urandom(600 * 1024)
    monkeypatch.setattr(mise_a_jour, "_ouvrir", servir(donnees))
    assert mise_a_jour.telecharger(fichier_publie(donnees), tmp_path, lambda _part: None, lambda: True) is None


def test_preparer(monkeypatch, tmp_path):
    donnees = os.urandom(600 * 1024)
    monkeypatch.setattr(mise_a_jour, "_ouvrir", servir(donnees))
    app = application(tmp_path / "app", b"ancien", {})
    installateur = mise_a_jour.preparer(fichier_publie(donnees), app, lambda _part: None, lambda: False)
    assert installateur == app / ".mise-a-jour" / "BilanSantePC-Installation-v0.9.0.exe"
    assert installateur.read_bytes() == donnees
    assert (app / "BilanSantePC.exe").read_bytes() == b"ancien"  # rien de remplacé avant la fermeture


@pytest.mark.parametrize("arret, erreur", [(False, mise_a_jour.Invalide), (True, None)])
def test_preparer_efface_un_telechargement_rate_ou_arrete(monkeypatch, tmp_path, arret, erreur):
    donnees = os.urandom(600 * 1024)
    monkeypatch.setattr(mise_a_jour, "_ouvrir", servir(donnees))
    app = application(tmp_path / "app", b"ancien", {})
    publie = fichier_publie(donnees, empreinte="00" * 32)  # pas celui publié
    if erreur:
        with pytest.raises(erreur):
            mise_a_jour.preparer(publie, app, lambda _part: None, lambda: arret)
    else:
        assert mise_a_jour.preparer(publie, app, lambda _part: None, lambda: arret) is None
    assert not (app / ".mise-a-jour").exists()


def test_installable(monkeypatch, tmp_path):
    nouvelle = mise_a_jour.plus_recente([version("v99.0.0")], "0.3.8")
    assert not mise_a_jour.installable(nouvelle)  # depuis le code source : pas d'application installée
    assert mise_a_jour.installable(nouvelle, tmp_path)
    assert list(tmp_path.iterdir()) == []  # l'essai d'écriture ne laisse rien
    assert not mise_a_jour.installable(nouvelle | {"installateur": None}, tmp_path)

    def protege(*_args, **_options):
        raise PermissionError("Accès refusé")
    monkeypatch.setattr(Path, "touch", protege)
    assert not mise_a_jour.installable(nouvelle, tmp_path)  # dossier protégé (Program Files…)


def test_lancer_installation(monkeypatch, tmp_path):
    lancements = []
    monkeypatch.setattr(mise_a_jour, "_lancer", lambda arguments, dossier: lancements.append((arguments, dossier)))
    installateur = tmp_path / ".mise-a-jour" / "BilanSantePC-Installation-v0.9.0.exe"
    mise_a_jour.lancer_installation(installateur, tmp_path)
    assert lancements == [([str(installateur), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/DIR={tmp_path}",
                            f"/ATTENDRE={os.getpid()}"], installateur.parent)]


def test_l_installateur_parle_comme_l_application():
    """installateur.iss lit /ATTENDRE, rouvre l'application avec les mêmes arguments et porte le nom cherché."""
    script = (Path(mise_a_jour.__file__).parent.parent / "installateur.iss").read_text(encoding="utf-8-sig")
    assert "{param:ATTENDRE|0}" in script
    assert f'Parameters: "{mise_a_jour.ARGUMENT_FAITE}"' in script and f"'{mise_a_jour.ARGUMENT_RATEE}'" in script
    assert re.search(rf"^OutputBaseFilename={mise_a_jour.PREFIXE_INSTALLATEUR}v\{{#Version}}$", script, re.MULTILINE)
    assert f"{{app}}\\{mise_a_jour.NOM_EXE}" in script
    assert f"{{app}}\\{mise_a_jour.TEMPORAIRE}" in script and f"{{app}}\\{mise_a_jour.ANCIENNE}" in script


def test_environnement_d_une_autre_copie(monkeypatch, tmp_path):
    interne = str(tmp_path / "_internal")
    monkeypatch.setattr(sys, "_MEIPASS", interne, raising=False)
    monkeypatch.setenv("PATH", os.pathsep.join([interne, r"C:\Windows"]))
    monkeypatch.setenv("QT_PLUGIN_PATH", interne + r"\PySide6\plugins")
    environnement = mise_a_jour._environnement()
    assert environnement["PATH"] == r"C:\Windows" and "QT_PLUGIN_PATH" not in environnement
    assert environnement["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


def test_nettoyer(tmp_path):
    app = application(tmp_path / "app", b"exe", {})
    for nom in (".mise-a-jour", ".ancienne-version"):
        (app / nom / "_internal").mkdir(parents=True)
    mise_a_jour.nettoyer(app)
    assert sorted(chemin.name for chemin in app.iterdir()) == ["BilanSantePC.exe", "_internal"]
    mise_a_jour.nettoyer()  # depuis le code source : rien à effacer, rien ne plante
