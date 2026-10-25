"""Tests des mises à jour, sans réseau et sans toucher à l'application installée. Lancer avec : python -m pytest"""

import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile
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


def version(tag: str, brouillon: bool = False, avec_zip: bool = True, notes: str = "- Nouveauté") -> dict:
    """Une version publiée, telle que la liste de GitHub la décrit."""
    nom = f"BilanSantePC-{tag}-windows.zip"
    fichiers = [{"name": nom, "size": 10, "digest": "sha256:" + "AB" * 32,
                 "browser_download_url": f"{mise_a_jour.ORIGINE_ZIP}{tag}/{nom}"}] if avec_zip else []
    return {"tag_name": tag, "draft": brouillon, "prerelease": True, "body": notes, "assets": fichiers,
            "html_url": f"https://github.com/{mise_a_jour.DEPOT}/releases/tag/{tag}"}


def zip_application(chemin: Path, fichiers: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(chemin, "w") as archive:
        for nom, contenu in fichiers.items():
            archive.writestr(nom, contenu)
    return chemin


def servir(contenu: bytes):
    """Remplace la réponse de GitHub par `contenu`."""
    return lambda _url: io.BytesIO(contenu)


def fichier_publie(contenu: bytes, **valeurs) -> dict:
    return {"nom": "BilanSantePC-v0.9.0-windows.zip", "taille": len(contenu),
            "url": f"{mise_a_jour.ORIGINE_ZIP}v0.9.0/BilanSantePC-v0.9.0-windows.zip",
            "empreinte": hashlib.sha256(contenu).hexdigest()} | valeurs


def application(dossier: Path, exe: bytes, interne: dict[str, bytes]) -> Path:
    """Un dossier d'application : le .exe et son dossier _internal."""
    (dossier / "_internal").mkdir(parents=True)
    (dossier / mise_a_jour.NOM_EXE).write_bytes(exe)
    for nom, contenu in interne.items():
        (dossier / "_internal" / nom).write_bytes(contenu)
    return dossier


def contenu(dossier: Path) -> dict[str, bytes]:
    return {str(chemin.relative_to(dossier)): chemin.read_bytes() for chemin in dossier.rglob("*") if chemin.is_file()}


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
    assert nouvelle["zip"]["url"].endswith("/v0.3.10/BilanSantePC-v0.3.10-windows.zip")


@pytest.mark.parametrize("actuelle, publiees, attendu", [
    ("0.3.8", ["v0.3.8", "v0.3.7"], None),
    ("0.3.6.1", ["v0.3.6"], None),
    ("0.3.6", ["v0.3.6.1"], "0.3.6.1"),
    ("0.3.8", [], None),
])
def test_deja_a_jour_ou_pas(actuelle, publiees, attendu):
    nouvelle = mise_a_jour.plus_recente([version(tag) for tag in publiees], actuelle)
    assert (nouvelle and nouvelle["version"]) == attendu


def test_zip_de_la_version():
    assert mise_a_jour.zip_de(version("v0.9.0")) == {
        "nom": "BilanSantePC-v0.9.0-windows.zip", "taille": 10, "empreinte": "ab" * 32,
        "url": f"{mise_a_jour.ORIGINE_ZIP}v0.9.0/BilanSantePC-v0.9.0-windows.zip"}
    assert mise_a_jour.zip_de(version("v0.9.0", avec_zip=False)) is None
    sans_empreinte = version("v0.9.0")
    sans_empreinte["assets"][0]["digest"] = None
    assert mise_a_jour.zip_de(sans_empreinte) is None  # sans empreinte, pas d'installation automatique
    ailleurs = version("v0.9.0")
    ailleurs["assets"][0]["browser_download_url"] = "https://exemple.com/BilanSantePC-v0.9.0-windows.zip"
    assert mise_a_jour.zip_de(ailleurs) is None


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


def test_decompresser(tmp_path):
    archive = zip_application(tmp_path / "a.zip", {"BilanSantePC/BilanSantePC.exe": b"exe",
                                                   "BilanSantePC/_internal/a.txt": b"a", "../dehors.txt": b"non"})
    dossier = mise_a_jour.decompresser(archive, tmp_path / "dest")
    assert dossier == tmp_path / "dest" / "BilanSantePC"
    assert contenu(dossier) == {"BilanSantePC.exe": b"exe", str(Path("_internal/a.txt")): b"a"}
    assert not (tmp_path / "dehors.txt").exists()  # rien d'écrit hors du dossier de destination


def test_decompresser_refuse_un_zip_sans_l_application(tmp_path):
    archive = zip_application(tmp_path / "a.zip", {"autre/programme.exe": b"exe"})
    with pytest.raises(mise_a_jour.Invalide):
        mise_a_jour.decompresser(archive, tmp_path / "dest")


def test_preparer(monkeypatch, tmp_path):
    donnees = zip_application(tmp_path / "a.zip", {"BilanSantePC/BilanSantePC.exe": b"neuf"}).read_bytes()
    monkeypatch.setattr(mise_a_jour, "_ouvrir", servir(donnees))
    app = application(tmp_path / "app", b"ancien", {})
    exe = mise_a_jour.preparer(fichier_publie(donnees), app, lambda _part: None, lambda: False)
    assert exe == app / ".mise-a-jour" / "BilanSantePC" / "BilanSantePC.exe" and exe.read_bytes() == b"neuf"
    assert [chemin.name for chemin in (app / ".mise-a-jour").iterdir()] == ["BilanSantePC"]  # zip effacé
    assert (app / "BilanSantePC.exe").read_bytes() == b"ancien"  # rien de remplacé avant la fermeture


@pytest.mark.parametrize("arret, erreur", [(False, mise_a_jour.Invalide), (True, None)])
def test_preparer_efface_un_telechargement_rate_ou_arrete(monkeypatch, tmp_path, arret, erreur):
    donnees = zip_application(tmp_path / "a.zip", {"autre.exe": b"x"}).read_bytes()
    monkeypatch.setattr(mise_a_jour, "_ouvrir", servir(donnees))
    app = application(tmp_path / "app", b"ancien", {})
    if erreur:
        with pytest.raises(erreur):
            mise_a_jour.preparer(fichier_publie(donnees), app, lambda _part: None, lambda: arret)
    else:
        assert mise_a_jour.preparer(fichier_publie(donnees), app, lambda _part: None, lambda: arret) is None
    assert not (app / ".mise-a-jour").exists()


def test_installable(monkeypatch, tmp_path):
    nouvelle = mise_a_jour.plus_recente([version("v99.0.0")], "0.3.8")
    assert not mise_a_jour.installable(nouvelle)  # depuis le code source : pas d'application installée
    assert mise_a_jour.installable(nouvelle, tmp_path)
    assert list(tmp_path.iterdir()) == []  # l'essai d'écriture ne laisse rien
    assert not mise_a_jour.installable(nouvelle | {"zip": None}, tmp_path)

    def protege(*_args, **_options):
        raise PermissionError("Accès refusé")
    monkeypatch.setattr(Path, "touch", protege)
    assert not mise_a_jour.installable(nouvelle, tmp_path)  # dossier protégé (Program Files…)


def test_remplacer(tmp_path):
    app = application(tmp_path / "app", b"ancien", {"vieux.txt": b"v"})
    (app / "notes.txt").write_bytes(b"a moi")
    source = application(tmp_path / "source", b"neuf", {"neuf.txt": b"n"})
    assert mise_a_jour.remplacer(source, app)
    assert (app / "BilanSantePC.exe").read_bytes() == b"neuf"
    assert sorted(chemin.name for chemin in (app / "_internal").iterdir()) == ["neuf.txt"]
    assert (app / "notes.txt").read_bytes() == b"a moi"  # le reste du dossier n'est pas touché
    assert (app / ".ancienne-version" / "_internal" / "vieux.txt").read_bytes() == b"v"


def test_remplacer_remet_l_ancienne_version_en_cas_d_echec(monkeypatch, tmp_path):
    app = application(tmp_path / "app", b"ancien", {"vieux.txt": b"v"})
    avant = contenu(app)
    source = application(tmp_path / "source", b"neuf", {"neuf.txt": b"n"})

    def copie_ratee(source_, cible, **_options):
        (Path(cible) / "moitie.txt").parent.mkdir(parents=True)
        (Path(cible) / "moitie.txt").write_bytes(b"m")
        raise OSError("Disque plein")
    monkeypatch.setattr(mise_a_jour.shutil, "copytree", copie_ratee)
    assert not mise_a_jour.remplacer(source, app)
    assert {nom: donnees for nom, donnees in contenu(app).items() if not nom.startswith(".ancienne")} == avant


def installee(monkeypatch, tmp_path) -> Path:
    """Une application installée et sa nouvelle version, décompressée et lancée en mode installation."""
    app = application(tmp_path / "app", b"ancien", {"vieux.txt": b"v"})
    source = application(app / ".mise-a-jour" / "BilanSantePC", b"neuf", {"neuf.txt": b"n"})
    monkeypatch.setattr(sys, "executable", str(source / "BilanSantePC.exe"))
    return app


def test_installer(monkeypatch, tmp_path):
    app = installee(monkeypatch, tmp_path)
    lancements = []
    monkeypatch.setattr(mise_a_jour, "attendre_fermeture", lambda pid: pid == 1234)
    monkeypatch.setattr(mise_a_jour, "_lancer", lambda arguments, dossier: lancements.append((arguments, dossier)))
    assert mise_a_jour.installer_depuis(["BilanSantePC.exe", "--installer", str(app), "1234"]) == 0
    assert (app / "BilanSantePC.exe").read_bytes() == b"neuf"
    assert lancements == [([str(app / "BilanSantePC.exe"), mise_a_jour.ARGUMENT_FAITE], app)]


def test_installer_rate_rouvre_l_ancienne_version(monkeypatch, tmp_path):
    app = installee(monkeypatch, tmp_path)
    lancements = []
    monkeypatch.setattr(mise_a_jour, "attendre_fermeture", lambda _pid: True)
    monkeypatch.setattr(mise_a_jour, "remplacer", lambda _source, _app: False)
    monkeypatch.setattr(mise_a_jour, "_lancer", lambda arguments, _dossier: lancements.append(arguments))
    assert not mise_a_jour.installer(app, 1234)
    assert lancements == [[str(app / "BilanSantePC.exe"), mise_a_jour.ARGUMENT_RATEE]]


def test_installer_attend_la_fermeture(monkeypatch, tmp_path):
    app = installee(monkeypatch, tmp_path)
    monkeypatch.setattr(mise_a_jour, "attendre_fermeture", lambda _pid: False)
    assert not mise_a_jour.installer(app, 1234)  # et rien n'est relancé (fixture)
    assert (app / "BilanSantePC.exe").read_bytes() == b"ancien"


def test_installer_refuse_un_autre_dossier(monkeypatch, tmp_path):
    app = installee(monkeypatch, tmp_path)
    autre = application(tmp_path / "autre", b"autre", {"x.txt": b"x"})
    monkeypatch.setattr(mise_a_jour, "attendre_fermeture", lambda _pid: True)
    assert not mise_a_jour.installer(autre, 1234)  # la mise à jour de `app` ne remplace pas `autre`
    assert (autre / "BilanSantePC.exe").read_bytes() == b"autre"
    monkeypatch.setattr(sys, "executable", str(tmp_path / "ailleurs" / "BilanSantePC.exe"))
    assert not mise_a_jour.installer(app, 1234)  # lancé d'ailleurs que du dossier temporaire
    assert (app / "BilanSantePC.exe").read_bytes() == b"ancien"


@pytest.mark.parametrize("arguments", [["--installer"], ["--installer", "C:\\app"], ["--installer", "C:\\app", "x"]])
def test_installer_avec_des_arguments_invalides(arguments):
    assert mise_a_jour.installer_depuis(["BilanSantePC.exe", *arguments]) == 1


def test_attendre_fermeture():
    fini = subprocess.Popen([sys.executable, "-c", "pass"])
    fini.wait()
    assert mise_a_jour.attendre_fermeture(fini.pid)  # déjà fermé
    actif = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert not mise_a_jour.attendre_fermeture(actif.pid, 0.2)
    finally:
        actif.kill()
        actif.wait()
    assert mise_a_jour.attendre_fermeture(actif.pid)


def test_lancer_installation(monkeypatch, tmp_path):
    lancements = []
    monkeypatch.setattr(mise_a_jour, "_lancer", lambda arguments, dossier: lancements.append((arguments, dossier)))
    exe = tmp_path / ".mise-a-jour" / "BilanSantePC" / "BilanSantePC.exe"
    mise_a_jour.lancer_installation(exe, tmp_path)
    assert lancements == [([str(exe), "--installer", str(tmp_path), str(os.getpid())], exe.parent)]


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
