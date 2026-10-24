"""Tests de l'onglet Stockage, sans l'afficher à l'écran. Lancer avec : python -m pytest"""

import importlib
import os
import time
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from modules import doublons, stockage
from modules import fichiers as module_fichiers
from tests.test_interface import app, corbeille_protegee, fenetre, rien_ne_s_ouvre  # noqa: F401 (fixtures)
from tests.test_stockage import UTILISE, Usage, disque  # noqa: F401 (fixture)
from ui import fenetre as fenetre_module
from ui import stockage as page_stockage
from ui.stockage import HAUTEUR_LIBRE, LigneElement


def resultat_du_faux_disque(racine) -> dict:
    """Ce que la page reçoit à la fin de l'analyse du faux disque."""
    return stockage.scan(str(racine)) | {"date": datetime(2026, 10, 24, 18, 30)}


def attendre(condition, delai: int = 5000) -> None:
    """Laisse Qt tourner jusqu'à ce que `condition()` soit vraie (au plus `delai` millisecondes).

    Pas QTest.qWait : il garde le verrou de Python et le thread d'analyse n'avance presque plus.
    """
    fin = time.monotonic() + delai / 1000
    while not condition():
        assert time.monotonic() < fin, "attente trop longue"
        QApplication.processEvents()
        time.sleep(0.01)  # rend la main au thread d'analyse


def lent(_racine, progression, arret):
    """Analyse qui ne finit que si on l'arrête."""
    progression(1024, 1)
    while not arret():
        time.sleep(0.01)
    return None


def test_onglets(fenetre):
    assert fenetre.pages.currentIndex() == 0
    fenetre.groupe_onglets.button(fenetre_module.ONGLET_STOCKAGE).click()
    assert fenetre.pages.currentIndex() == fenetre.onglet == fenetre_module.ONGLET_STOCKAGE
    fenetre.groupe_onglets.button(0).click()
    voir = next(b for b in fenetre.cartes["disque"].findChildren(QPushButton)
                if b.text() == "Voir ce qui prend de la place")
    voir.click()  # depuis la carte Disque du bilan
    assert fenetre.pages.currentIndex() == fenetre_module.ONGLET_STOCKAGE
    assert fenetre.groupe_onglets.checkedId() == fenetre_module.ONGLET_STOCKAGE


def test_avant_analyse(fenetre):
    page = fenetre.stockage
    assert page.bouton.text().strip() == "Analyser le stockage"
    assert all(section.isHidden() for section in page.sections)
    assert page.etat.text() in page_stockage.ETATS.values()  # remplissage du disque lu tout de suite


def test_affichage(fenetre, disque):
    page = fenetre.stockage
    page.afficher(resultat_du_faux_disque(disque), animer=False)
    lignes = page.lignes_categories()
    assert len(lignes) == 12
    # Du plus gros au plus petit.
    assert [ligne.categorie["cle"] for ligne in lignes[:3]] == ["systeme", "jeux", "videos"]
    plus_gros = [page.liste_plus_gros.itemAt(i).widget() for i in range(page.liste_plus_gros.count())]
    noms = [ligne.findChildren(page_stockage.TexteCoupe)[0].text() for ligne in plus_gros]
    # Toutes catégories confondues, sauf Système (rien à y faire), dans la limite de NB_PLUS_GROS.
    assert noms == ["Jeu", "film.mkv", "setup.exe", "Editeur", "Windows.old", "Discord", "Discord › Cache", ".ollama"]
    assert page.info.text() == "Analyse du 24/10/2026 à 18:30 : 13 fichiers parcourus en 0 s."
    assert page.bouton.text().strip() == "Relancer l'analyse"


def test_categorie_qui_se_deplie(fenetre, disque):
    page = fenetre.stockage
    page.afficher(resultat_du_faux_disque(disque), animer=False)
    jeux = next(ligne for ligne in page.lignes_categories() if ligne.categorie["cle"] == "jeux")
    assert jeux.detail.maximumHeight() == 0
    QTest.keyClick(jeux, Qt.Key.Key_Space)  # au clavier aussi
    QTest.qWait(350)
    assert jeux.ouvert and jeux.detail.maximumHeight() == HAUTEUR_LIBRE
    assert [e.findChild(QPushButton).text() for e in jeux.detail.findChildren(LigneElement)] == ["Afficher"]
    jeux.basculer()
    QTest.qWait(350)
    assert not jeux.ouvert and jeux.detail.maximumHeight() == 0


def test_afficher_dans_l_explorateur(fenetre, disque, monkeypatch):
    """« Afficher » ouvre seulement l'Explorateur : le dossier, ou celui du fichier avec le fichier choisi."""
    appels = []
    monkeypatch.setattr(os, "startfile", lambda chemin: appels.append(("dossier", chemin)))
    monkeypatch.setattr(page_stockage.subprocess, "Popen", lambda arguments: appels.append(("fichier", arguments)))
    page = fenetre.stockage
    page.afficher(resultat_du_faux_disque(disque), animer=False)
    premier = page.liste_plus_gros.itemAt(0).widget()  # le jeu, un dossier
    premier.findChild(QPushButton).click()
    film = str(disque / "Users" / "moi" / "Videos" / "film.mkv")
    page.montrer(film, dossier=False)
    jeu = str(disque / "Program Files (x86)" / "Steam" / "steamapps" / "common" / "Jeu")
    assert appels == [("dossier", jeu), ("fichier", ["explorer", "/select,", film])]


def test_emplacement_introuvable(fenetre, monkeypatch):
    def refuse(_chemin):
        raise OSError("introuvable")
    monkeypatch.setattr(os, "startfile", refuse)
    fenetre.stockage.montrer(r"C:\nulle\part", dossier=True)
    assert fenetre.statusBar().currentMessage() == "Cet emplacement n'a pas pu s'ouvrir."


def test_analyse_en_arriere_plan(fenetre, app, disque):
    page = fenetre.stockage
    page.racine = str(disque)
    page.lancer()
    assert page.en_cours() and not fenetre.mode.isEnabled()  # pas de changement de mode pendant l'analyse
    assert page.bouton.text().strip() == "Arrêter l'analyse"
    attendre(lambda: page.resultat is not None, 5000)
    assert not page.en_cours() and fenetre.mode.isEnabled()
    assert page.resultat["utilise"] == UTILISE and page.progression.isHidden()
    assert fenetre.statusBar().currentMessage().startswith("Stockage analysé en")


def test_arreter_l_analyse(fenetre, disque, monkeypatch):
    monkeypatch.setattr(stockage, "scan", lent)
    page = fenetre.stockage
    page.lancer()
    page.lancer()  # le même bouton arrête
    assert page.bouton.text().strip() == "Arrêt en cours…" and not page.bouton.isEnabled()
    attendre(lambda: not page.en_cours() and page.bouton.isEnabled(), 5000)
    QTest.qWait(50)
    assert page.resultat is None and page.bouton.text().strip() == "Analyser le stockage"
    assert fenetre.statusBar().currentMessage() == "Analyse du stockage arrêtée."


def test_analyse_en_erreur(fenetre, monkeypatch):
    def plante(*_):
        raise RuntimeError("disque débranché")
    monkeypatch.setattr(stockage, "scan", plante)
    page = fenetre.stockage
    page.lancer()
    attendre(lambda: not page.en_cours() and page.bouton.isEnabled(), 5000)
    QTest.qWait(50)
    assert page.info.text().startswith("L'analyse du stockage n'a pas pu aboutir.")
    assert page.info.objectName() == "erreur" and all(section.isHidden() for section in page.sections)


def test_fermer_pendant_l_analyse(fenetre, monkeypatch):
    monkeypatch.setattr(stockage, "scan", lent)
    fenetre.stockage.lancer()
    fenetre.close()  # arrête l'analyse et attend le thread : pas de plantage de Qt
    assert not fenetre.stockage.travail.isRunning()


def test_resultat_garde_au_changement_de_mode(fenetre, disque):
    from ui import theme
    fenetre.changer_page(fenetre_module.ONGLET_STOCKAGE)
    resultat = resultat_du_faux_disque(disque)
    fenetre.stockage.afficher(resultat, animer=False)
    fenetre.show()
    try:
        fenetre.mode.click()
        QTest.qWait(fenetre_module.DUREE_FONDU + 200)
        assert fenetre.stockage.resultat is resultat and len(fenetre.stockage.lignes_categories()) == 12
        assert fenetre.pages.currentIndex() == fenetre_module.ONGLET_STOCKAGE  # on reste sur l'onglet
    finally:
        theme.fichier_reglages().unlink(missing_ok=True)
        importlib.reload(theme)  # les autres tests retrouvent le mode de Windows


def test_textes():
    assert page_stockage.nombre_lisible(584684) == "584\u202f684"
    assert page_stockage.part_lisible(0, 100) == "0 %" and page_stockage.part_lisible(1, 1000) == "moins de 1 %"
    assert page_stockage.part_lisible(49, 100) == "49 %"
    assert [page_stockage.niveau_remplissage(p) for p in (50, 80, 96)] == ["vert", "orange", "rouge"]


def lent_doublons(_personnels, progression, arret):
    """Recherche de doublons qui ne finit que si on l'arrête."""
    progression("rapide", 1, 2)
    while not arret():
        time.sleep(0.01)
    return None


def test_recherche_des_doublons(fenetre, disque, monkeypatch):
    monkeypatch.setattr(doublons, "TAILLE_MIN_FICHIER", 100)
    film = disque / "Users" / "moi" / "Videos" / "film.mkv"
    (disque / "Users" / "moi" / "Downloads" / "film (copie).mkv").write_bytes(film.read_bytes())
    page = fenetre.stockage
    page.afficher(resultat_du_faux_disque(disque), animer=False)
    assert not page.intro_doublons.isHidden() and page.bouton_doublons.text().strip() == "Chercher les doublons"
    page.chercher_doublons()
    assert page.en_cours() and not fenetre.mode.isEnabled() and not page.bouton.isEnabled()  # une chose à la fois
    attendre(lambda: not page.en_cours())
    assert fenetre.mode.isEnabled() and page.bouton.isEnabled()
    assert page.resume_doublons.text() == "1 groupe en double : jusqu'à 300 octets à récupérer"
    assert page.intro_doublons.isHidden() and page.bouton_doublons.text().strip() == "Relancer la recherche"
    (ligne,) = page.lignes_doublons()
    copies = [e.findChildren(page_stockage.TexteCoupe)[0].text() for e in ligne.detail.findChildren(LigneElement)]
    assert copies == ["Dans Téléchargements", "Dans Vidéos"]


def test_arreter_la_recherche_des_doublons(fenetre, disque, monkeypatch):
    monkeypatch.setattr(doublons, "chercher", lent_doublons)
    page = fenetre.stockage
    page.afficher(resultat_du_faux_disque(disque), animer=False)
    page.chercher_doublons()
    page.chercher_doublons()  # le même bouton arrête
    assert page.bouton_doublons.text().strip() == "Arrêt en cours…"
    attendre(lambda: not page.en_cours() and page.bouton_doublons.isEnabled())
    QTest.qWait(50)
    assert page.doublons is None and page.bouton_doublons.text().strip() == "Chercher les doublons"
    assert fenetre.statusBar().currentMessage() == "Recherche des doublons arrêtée."


def test_recherche_des_doublons_en_erreur(fenetre, disque, monkeypatch):
    def plante(*_):
        raise RuntimeError("fichier disparu")
    monkeypatch.setattr(doublons, "chercher", plante)
    page = fenetre.stockage
    page.afficher(resultat_du_faux_disque(disque), animer=False)
    page.chercher_doublons()
    attendre(lambda: not page.en_cours())
    QTest.qWait(50)
    assert page.info_doublons.text().startswith("La recherche des doublons n'a pas pu aboutir.")
    assert page.info_doublons.objectName() == "erreur" and not page.info_doublons.isHidden()


def test_nouvelle_analyse_oublie_les_doublons(fenetre, disque):
    """Après une nouvelle analyse du disque, les fichiers ont pu changer : les doublons sont à chercher à nouveau."""
    page = fenetre.stockage
    page.doublons = {"groupes": [], "nombre": 0, "en_trop": 0, "duree": 1.0}
    page.afficher(resultat_du_faux_disque(disque), animer=False)
    assert page.resume_doublons.text() == "Aucun doublon d'au moins 1 Mo dans tes fichiers personnels."
    page.fin(stockage.scan(str(disque)))
    assert page.doublons is None and not page.intro_doublons.isHidden()


def boutons_supprimer(widget) -> list[QPushButton]:
    return widget.findChildren(QPushButton, "supprimer")


def textes(ligne) -> list[str]:
    return [texte.text() for texte in ligne.findChildren(page_stockage.TexteCoupe)]


def test_supprimer_seulement_les_fichiers_personnels(fenetre, disque):
    page = fenetre.stockage
    page.afficher(resultat_du_faux_disque(disque), animer=False)
    avec = [textes(ligne)[0] for ligne in page_stockage.lignes(page.liste_plus_gros) if boutons_supprimer(ligne)]
    assert avec == ["film.mkv", "setup.exe"]  # pas le jeu, les logiciels, les caches ni Windows.old


def taille(page, cle: str) -> int:
    return next(c["taille"] for c in page.resultat["categories"] if c["cle"] == cle)


def test_supprimer(fenetre, disque, monkeypatch):
    film = disque / "Users" / "moi" / "Videos" / "film.mkv"
    page = fenetre.stockage
    page.afficher(resultat_du_faux_disque(disque), animer=False)
    supprimes, confirmations = [], []
    monkeypatch.setattr(module_fichiers, "supprimer", lambda chemin, _fenetre: supprimes.append(chemin) or
                        os.remove(chemin))
    monkeypatch.setattr(stockage.psutil, "disk_usage", lambda _: Usage(20_000, UTILISE - 300, 10_300, 48.5))
    monkeypatch.setattr(page, "confirmer_suppression", lambda *arguments: confirmations.append(arguments) or True)
    systeme = taille(page, "systeme")
    videos = next(ligne for ligne in page.lignes_categories() if ligne.categorie["cle"] == "videos")
    videos.basculer()
    boutons_supprimer(videos)[0].click()
    assert confirmations == [(str(film), False, 300, 1)] and supprimes == [str(film)]
    videos = next(ligne for ligne in page.lignes_categories() if ligne.categorie["cle"] == "videos")
    assert videos.ouvert and videos.categorie["taille"] == 0  # toujours dépliée, à jour
    assert taille(page, "corbeille") == 25 and taille(page, "systeme") == systeme  # rien ne passe par la Corbeille
    assert page.utilise.text() == "9,5 Ko utilisés"  # 9 700 octets : la place est libérée
    assert "film.mkv" not in [textes(ligne)[0] for ligne in page_stockage.lignes(page.liste_plus_gros)]
    assert fenetre.statusBar().currentMessage() == "« film.mkv » supprimé : 300 octets libérés."


def test_suppression_annulee(fenetre, disque, monkeypatch):
    page = fenetre.stockage
    page.afficher(resultat_du_faux_disque(disque), animer=False)
    monkeypatch.setattr(page, "confirmer_suppression", lambda *_: False)
    film = disque / "Users" / "moi" / "Videos" / "film.mkv"
    page.supprimer(str(film), False)  # supprimer pour de vrai est interdit pendant les tests
    assert film.exists() and taille(page, "videos") == 300


def test_suppression_refusee_par_windows(fenetre, disque, monkeypatch):
    """Fichier ouvert dans un programme, accès refusé… : Windows le dit, rien ne change ici."""
    page = fenetre.stockage
    page.afficher(resultat_du_faux_disque(disque), animer=False)
    monkeypatch.setattr(page, "confirmer_suppression", lambda *_: True)
    monkeypatch.setattr(module_fichiers, "supprimer", lambda *_: None)
    page.supprimer(str(disque / "Users" / "moi" / "Videos" / "film.mkv"), False)
    assert fenetre.statusBar().currentMessage() == ("« film.mkv » n'a pas été supprimé : il est peut-être ouvert "
                                                    "dans un programme.")
    assert taille(page, "videos") == 300


def test_supprimer_un_doublon(fenetre, disque, monkeypatch):
    monkeypatch.setattr(doublons, "TAILLE_MIN_FICHIER", 100)
    film = disque / "Users" / "moi" / "Videos" / "film.mkv"
    copie = disque / "Users" / "moi" / "Downloads" / "film (copie).mkv"
    copie.write_bytes(film.read_bytes())
    page = fenetre.stockage
    page.afficher(resultat_du_faux_disque(disque), animer=False)
    page.doublons = doublons.chercher(page.resultat["personnels"])
    page._afficher_doublons(animer=False)
    monkeypatch.setattr(module_fichiers, "supprimer", lambda chemin, _fenetre: os.remove(chemin))
    monkeypatch.setattr(page, "confirmer_suppression", lambda *_: True)
    (ligne,) = page.lignes_doublons()
    premier, second = boutons_supprimer(ligne)  # chaque copie a le sien
    premier.click()  # celle de Téléchargements
    assert not copie.exists() and film.exists()
    assert page.lignes_doublons() == []  # plus qu'un exemplaire : plus en double
    assert page.resume_doublons.text() == "Aucun doublon d'au moins 1 Mo dans tes fichiers personnels."


def test_pas_de_suppression_pendant_une_analyse(fenetre, disque, monkeypatch):
    monkeypatch.setattr(doublons, "chercher", lent_doublons)
    page = fenetre.stockage
    page.afficher(resultat_du_faux_disque(disque), animer=False)
    page.chercher_doublons()
    assert boutons_supprimer(page) and not any(bouton.isEnabled() for bouton in boutons_supprimer(page))
    page.chercher_doublons()  # arrête la recherche
    attendre(lambda: not page.en_cours())
    assert all(bouton.isEnabled() for bouton in boutons_supprimer(page))


def test_confirmation(fenetre, monkeypatch):
    boites = []
    monkeypatch.setattr(page_stockage.QMessageBox, "exec", lambda boite: boites.append(boite) or 0)
    confirme = fenetre.stockage.confirmer_suppression(r"C:\Users\moi\Pictures\Vacances", True, 3 * 1024**3, 124)
    (boite,) = boites
    assert not confirme  # fermée sans cliquer : rien n'est supprimé
    assert boite.text() == "Supprimer définitivement le dossier « Vacances » (124 fichiers, 3,0 Go) ?"
    assert boite.informativeText().startswith("Emplacement : C:\\Users\\moi\\Pictures")
    assert "impossible de le récupérer" in boite.informativeText()
    assert boite.defaultButton().text() == "Annuler"


def test_progression_des_doublons(fenetre):
    page = fenetre.stockage
    page.avancer_doublons(("rapide", 5, 10))
    assert page.info_doublons.text() == "Comparaison rapide : 5 fichiers sur 10…"
    assert page.glissement_doublons.endValue() == 50
    page.avancer_doublons(("contenu", 512, 1024))
    assert page.info_doublons.text() == "Lecture du contenu : 512 octets sur 1,0 Ko…"
    assert page.glissement_doublons.endValue() == 550
