"""Tests de la fenêtre, sans l'afficher à l'écran. Lancer avec : python -m pytest"""

import importlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # avant d'importer Qt : aucune fenêtre visible

import pytest
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QHelpEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QToolTip, QTreeWidget, QTreeWidgetItem, QWidget

import historique
from modules import fichiers as module_fichiers
from tests.test_analyse import faux_modules, plante
from tests.test_score import GO, batterie, demarrage, disque, fichiers
from ui import analyse
from ui.fenetre import Fenetre, preparer_application
from ui.widgets import Carte, Feuille, Fondu, Graphique, Infobulle, Logo, texte_infobulle
from ui import fenetre as fenetre_module


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    preparer_application(application)
    return application


@pytest.fixture(autouse=True)
def corbeille_protegee(monkeypatch):
    """Aucun test ne doit vider la vraie Corbeille ni supprimer un vrai fichier : il faut remplacer
    vider_corbeille et supprimer explicitement."""
    def interdit(*_):
        raise AssertionError("un test a tenté de vider la vraie Corbeille ou de supprimer un fichier")
    monkeypatch.setattr(module_fichiers, "vider_corbeille", interdit)
    monkeypatch.setattr(module_fichiers, "supprimer", interdit)


@pytest.fixture(autouse=True)
def rien_ne_s_ouvre(monkeypatch):
    """Aucun test n'ouvre les Paramètres ou un dossier pour de vrai : remplacer os.startfile explicitement."""
    def interdit(*_):
        raise AssertionError("un test a tenté d'ouvrir une page ou un dossier")
    monkeypatch.setattr(os, "startfile", interdit)


@pytest.fixture
def fenetre(app, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))  # historique de test, pas celui de l'utilisateur
    resultat = Fenetre()
    yield resultat
    resultat.close()


def analyse_faite(tmp_path) -> dict:
    """Ce que le thread d'analyse envoie à la fenêtre."""
    resultat = analyse.analyser()
    resultat["historique"] = historique.enregistrer(resultat, tmp_path)
    resultat["comparaison"] = historique.comparer(resultat["historique"], analyse.NOMS)
    return resultat


def test_etat_initial(fenetre):
    assert not fenetre.copier.isEnabled() and not fenetre.enregistrer.isEnabled()
    assert fenetre.cartes["batterie"].isHidden()
    assert fenetre.jauge.texte_vide == "–"
    assert "Aucune analyse enregistrée" in fenetre.comparaison.text()


def test_analyse_complete(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch, demarrage=lambda: {"constats": ["c"], **demarrage(40)},
                 disque=lambda: {"constats": ["c"], **disque(90)})
    resultat = analyse_faite(tmp_path)
    fenetre.afficher(resultat)
    assert fenetre.jauge.note == analyse.score_global(resultat) == 0 + 6 + 25 + 15
    assert fenetre.etat.text() == "À améliorer" and fenetre.etat.property("niveau") == "rouge"
    assert fenetre.cartes["demarrage"].points.text() == "0 / 30"
    assert fenetre.cartes["fichiers"].points.text() == "hors score"
    assert fenetre.cartes["fichiers"].barre.isHidden() and not fenetre.cartes["disque"].barre.isHidden()
    assert fenetre.cartes["batterie"].isHidden()  # PC fixe
    assert fenetre.liste_conseils.count() == len(analyse.conseils(resultat)) == 2
    assert fenetre.copier.isEnabled() and fenetre.enregistrer.isEnabled()
    assert fenetre.info.text().startswith("Analyse du")

    fenetre.afficher(resultat)  # relancer ne doit pas empiler les conseils
    assert fenetre.liste_conseils.count() == 2


def test_tous_les_modules_en_erreur(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch, **{cle: plante for cle, _, _ in analyse.MODULES})
    fenetre.afficher(analyse_faite(tmp_path))
    assert fenetre.jauge.note is None and fenetre.jauge.texte_vide == "?"
    assert fenetre.etat.text() == "Analyse incomplète"
    assert all(carte.points.text() == "erreur" for carte in fenetre.cartes.values())
    assert "pas enregistrée" in fenetre.comparaison.text()


def test_batterie_affichee(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch, batterie=lambda: {"constats": ["b"], **batterie(0.5)})
    fenetre.afficher(analyse_faite(tmp_path))
    assert not fenetre.cartes["batterie"].isHidden()
    assert fenetre.cartes["batterie"].points.text() == "4 / 15"



def test_famille_de_police(monkeypatch):
    from ui import theme
    # La plateforme hors écran des tests ne voit aucune police : on simule celles installées.
    monkeypatch.setattr(theme.QFontDatabase, "hasFamily", lambda nom: nom == "Segoe UI")
    theme.famille.cache_clear()
    try:
        assert theme.famille(("Segoe UI Variable Text", "Segoe UI")) == "Segoe UI"
        assert theme.famille(("Segoe Fluent Icons", "Segoe MDL2 Assets")) == "Segoe MDL2 Assets"
    finally:
        theme.famille.cache_clear()  # ne pas garder ce faux résultat pour les autres tests


def corbeille_simulee(monkeypatch, avant: float, apres: float) -> list:
    """Corbeille de `avant` Go, qui en contient `apres` une fois la confirmation de Windows passée.

    Renvoie les appels : ("vider", fenêtre) puis ("scan", résultat précédent transmis).
    """
    appels = []
    monkeypatch.setattr(module_fichiers, "corbeille", lambda *_: avant * GO)
    monkeypatch.setattr(module_fichiers, "vider_corbeille", lambda fenetre: appels.append(("vider", fenetre)))

    def scan(precedent=None):
        appels.append(("scan", precedent))
        return {"constats": ["apres"], **fichiers(apres)}
    monkeypatch.setattr(module_fichiers, "scan", scan)
    return appels


def test_vider_la_corbeille(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch, fichiers=lambda: {"constats": ["c"], **fichiers(2, temporaires=1)})
    fenetre.afficher(analyse_faite(tmp_path))
    assert fenetre.vider.isEnabled()
    appels = corbeille_simulee(monkeypatch, avant=2, apres=0)
    fenetre.vider.click()
    # Confirmation de Windows rattachée à notre fenêtre, puis temporaires repris sans les remesurer.
    assert appels[0] == ("vider", int(fenetre.winId()))
    assert appels[1][0] == "scan" and appels[1][1]["temporaires"] == 1 * GO
    assert "2,0 Go libérés" in fenetre.annonce.texte()
    assert fenetre.cartes["fichiers"].resume.text() == "apres"
    assert fenetre.vider.isHidden()  # Corbeille vide : plus rien à vider


def test_vidage_refuse(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch, fichiers=lambda: {"constats": ["c"], **fichiers(2)})
    fenetre.afficher(analyse_faite(tmp_path))
    corbeille_simulee(monkeypatch, avant=2, apres=2)
    fenetre.vider.click()
    assert fenetre.annonce.texte() == "La Corbeille n'a pas été vidée."
    assert fenetre.cartes["fichiers"].resume.text() == "c" and fenetre.vider.isEnabled()


def test_pas_de_bouton_si_corbeille_vide(fenetre, tmp_path, monkeypatch):
    assert fenetre.vider.isHidden() and fenetre.bouton_pilotes.isHidden()  # avant l'analyse : rien à faire
    faux_modules(monkeypatch)  # Corbeille vide par défaut
    fenetre.afficher(analyse_faite(tmp_path))
    assert fenetre.vider.isHidden()


def test_progression_affichee(fenetre):
    fini = QSignalSpy(fenetre.glissement.finished)
    fenetre.avancer(2, 6, "Disque")
    assert fenetre.progression.maximum() == 600  # en centièmes de partie : la barre glisse
    assert fini.wait(3000)  # attend la vraie fin du glissement : un délai fixe échouait sur un PC chargé
    assert fenetre.progression.value() == 200  # deux parties finies
    assert fenetre.info.text() == "En cours : Disque (2 parties sur 6 finies)…"


def test_panne_imprevue_de_l_analyse(fenetre, app, monkeypatch):
    """Même si l'analyse plante en dehors des modules, la fenêtre reçoit un résultat et ne reste pas bloquée."""
    monkeypatch.setattr(analyse, "analyser", lambda *_: plante())
    fenetre.lancer()
    fenetre.analyse.wait()
    app.processEvents()  # livre le signal de fin envoyé depuis le thread
    assert fenetre.bouton.isEnabled() and fenetre.jauge.note is None
    assert "n'a pas pu aboutir" in fenetre.liste_conseils.itemAt(0).widget().findChild(QLabel).text()


def test_analyse_en_arriere_plan(fenetre, app, monkeypatch):
    """Le vrai thread d'analyse : étapes puis résultat arrivent jusqu'à la fenêtre."""
    faux_modules(monkeypatch)
    fenetre.lancer()
    assert fenetre.phrase.text() == "Analyse de ton PC en cours…" and not fenetre.bouton.isEnabled()
    assert fenetre.etat.text() == "Analyse en cours"  # pas « Pas encore analysé » pendant l'analyse
    fenetre.analyse.wait()
    app.processEvents()  # livre les signaux envoyés depuis le thread
    assert fenetre.glissement.endValue() == (len(analyse.MODULES) - 1) * 100  # dernière étape reçue
    assert fenetre.jauge.note == 100 and fenetre.bouton.isEnabled() and fenetre.etat.text() == "Bon état"


def test_bouton_ouvrir_d_un_conseil(fenetre, tmp_path, monkeypatch):
    ouvertures = []
    monkeypatch.setattr(os, "startfile", ouvertures.append)
    faux_modules(monkeypatch, demarrage=lambda: {"constats": ["c"], **demarrage(40)})
    fenetre.afficher(analyse_faite(tmp_path))
    carte = fenetre.liste_conseils.itemAt(0).widget()
    assert carte.bouton.text().strip() == "Ouvrir les Paramètres"
    carte.bouton.click()
    assert ouvertures == ["ms-settings:startupapps"]


def test_ouverture_impossible(fenetre, monkeypatch):
    def echec(_):
        raise OSError("introuvable")
    monkeypatch.setattr(os, "startfile", echec)
    fenetre.ouvrir("ms-settings:inexistant")
    assert fenetre.annonce.texte() == "Cette page n'a pas pu s'ouvrir sur ce PC."


def test_couleurs_du_theme():
    from ui import theme
    assert isinstance(theme.windows_en_clair(), bool)
    assert theme.rgba("#34d399", 31) == "rgba(52, 211, 153, 31)"  # même rendu qu'avant en thème sombre


def test_icone_de_l_application(app, fenetre):
    from PySide6.QtCore import QSize
    from ui import theme
    assert theme.ICONE_APPLICATION.exists()
    tailles = app.windowIcon().availableSizes()
    assert QSize(16, 16) in tailles and QSize(256, 256) in tailles  # toutes les tailles de l'ico sont lues
    assert not fenetre.findChild(Logo).windowIcon().isNull()  # la même icône en tête de la fenêtre


def test_changer_de_mode(fenetre, app, tmp_path, monkeypatch):
    from ui import theme
    faux_modules(monkeypatch)
    fenetre.afficher(analyse_faite(tmp_path))
    depart = theme.CLAIR
    fenetre.show()  # tailles réelles, pour la position de défilement
    QTest.qWait(10)
    fenetre.pages.currentWidget().verticalScrollBar().setValue(300)
    try:
        fenetre.mode.click()
        QTest.qWait(50)  # le changement se fait juste après le clic, sous le fondu
        assert theme.CLAIR is not depart
        assert theme.mode_choisi() is theme.CLAIR  # choix retenu pour les prochains lancements
        assert fenetre.mode.toolTip() == ("Passer en mode sombre" if theme.CLAIR else "Passer en mode clair")
        assert fenetre.jauge.note == 100 and fenetre.jauge.valeur == 100  # affichée, sans se re-remplir
        assert fenetre.findChild(Fondu, "fondu").isVisible()  # fondu en cours
        QTest.qWait(fenetre_module.DUREE_FONDU + 200)
        assert fenetre.findChild(Fondu, "fondu") is None  # fondu terminé et retiré
        assert fenetre.pages.currentWidget().verticalScrollBar().value() == 300  # on reste au même endroit
        fenetre.lancer()
        assert not fenetre.mode.isEnabled()  # pas de changement pendant l'analyse
        fenetre.analyse.wait()
        app.processEvents()
        assert fenetre.mode.isEnabled()  # de nouveau possible une fois l'analyse finie
    finally:
        theme.fichier_reglages().unlink(missing_ok=True)
        importlib.reload(theme)  # les autres tests retrouvent le mode de Windows


class FenetresMontrees(QObject):
    """Note chaque fenêtre qui s'affiche : un widget montré avant d'avoir un parent s'ouvre en petite fenêtre à part."""

    def __init__(self) -> None:
        super().__init__()
        self.noms: list[str] = []

    def eventFilter(self, objet, evenement) -> bool:
        if evenement.type() == QEvent.Type.Show and isinstance(objet, QWidget) and objet.isWindow():
            self.noms.append(type(objet).__name__)
        return False


def test_aucune_petite_fenetre_au_changement_de_mode(app, tmp_path, monkeypatch):
    """Plusieurs disques (choix du disque), une nouvelle version (bouton « Mettre à jour ») et une confirmation avec
    précision : rien de tout cela ne doit apparaître, même un instant, hors de la fenêtre."""
    from modules import disque as module_disque
    from ui import theme
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    deux_disques = [{"disque": lettre, "total": 100 * GO, "utilise": 50 * GO, "libre": 50 * GO, "pourcentage": 50.0}
                    for lettre in ("C:\\", "D:\\")]
    monkeypatch.setattr(module_disque, "lister_disques", lambda: deux_disques)
    espion = FenetresMontrees()
    app.installEventFilter(espion)
    fenetre = Fenetre()
    try:
        fenetre.show()
        assert not fenetre.stockage.choix.isHidden()
        fenetre.nouvelle_version = {"version": "99.0.0"}
        fenetre.mode.click()
        QTest.qWait(50)  # contenu recréé : choix du disque et bouton « Mettre à jour » compris
        assert not fenetre.bouton_maj.isHidden()
        feuille = Feuille(fenetre, "Supprimer ?", "Texte", details="Précision")
        feuille.deleteLater()
        assert espion.noms == ["Fenetre"]
    finally:
        app.removeEventFilter(espion)
        fenetre.close()
        theme.fichier_reglages().unlink(missing_ok=True)
        importlib.reload(theme)  # les autres tests retrouvent le mode de Windows


def test_melange_des_couleurs_de_la_barre_de_titre():
    from PySide6.QtGui import QColor
    noir, blanc = QColor("#000000"), QColor("#ffffff")
    assert fenetre_module.melange(noir, blanc, 1.0) == noir  # début du fondu : l'ancienne couleur
    assert fenetre_module.melange(noir, blanc, 0.0) == blanc  # fin : la nouvelle
    assert fenetre_module.melange(noir, blanc, 0.5).red() == 128


def test_detail_qui_se_deplie_et_se_replie(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch, demarrage=lambda: {"constats": ["c"], **demarrage(3)})
    fenetre.afficher(analyse_faite(tmp_path))
    carte = fenetre.cartes["demarrage"]
    carte.bouton.click()
    assert carte.ouvert and not carte.detail.isHidden() and carte.bouton.text() == "Masquer le détail"
    QTest.qWait(400)
    assert carte.detail.height() == carte.hauteur_detail()  # ajusté à ses 3 lignes, sans place vide
    assert Carte.HAUTEUR_DETAIL_MIN <= carte.detail.height() < Carte.HAUTEUR_DETAIL_MAX
    assert carte.detail.topLevelItem(0).toolTip(2) == r"C:\p0.exe"  # texte complet au survol
    carte.bouton.click()
    QTest.qWait(400)
    assert not carte.ouvert and carte.detail.isHidden()


def test_infobulle_dans_le_style_de_l_application(fenetre):
    """Les infobulles passent toutes par Infobulle (plaque de verre arrondie), jamais par la bulle grise de Qt."""
    fenetre.show()
    QTest.qWait(10)
    bulle, mode = Infobulle.instance(), fenetre.mode
    centre = mode.rect().center()
    QApplication.sendEvent(mode, QHelpEvent(QEvent.Type.ToolTip, centre, mode.mapToGlobal(centre)))
    assert bulle.isVisible() and bulle.texte == mode.toolTip() and not QToolTip.isVisible()
    assert bulle.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # rien autour des coins arrondis
    QApplication.sendEvent(mode, QEvent(QEvent.Type.Leave))
    assert not bulle.isVisible()


def test_infobulle_d_une_cellule_seulement_si_elle_est_coupee(app):
    tableau = QTreeWidget(columnCount=1, textElideMode=Qt.TextElideMode.ElideMiddle)
    long = r"C:\Users\moi\AppData\Local\Programs\Un logiciel au nom très long\lanceur.exe"
    lignes = [QTreeWidgetItem([texte]) for texte in ("Court", long, "Lanceur")]
    for ligne in lignes[:2]:
        ligne.setToolTip(0, ligne.text(0))  # infobulle qui répète le texte de la cellule
    lignes[2].setToolTip(0, "Explication en plus")
    tableau.addTopLevelItems(lignes)
    tableau.resize(220, 160)
    tableau.show()
    QTest.qWait(10)
    entier, coupe, explication = (texte_infobulle(tableau.viewport(), tableau.visualItemRect(ligne).center())
                                  for ligne in lignes)
    assert entier.texte == ""  # écrit en entier : rien à répéter
    assert coupe.texte == long and coupe.ancre is not None  # coupé : complet au survol, posé par-dessus lui
    assert explication.texte == "Explication en plus" and explication.ancre is None  # sous le pointeur
    tableau.close()


def test_conseils_qui_apparaissent_en_fondu(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch, demarrage=lambda: {"constats": ["c"], **demarrage(40)})
    fenetre.afficher(analyse_faite(tmp_path))
    premiere = fenetre.liste_conseils.itemAt(0).widget()
    assert premiere.graphicsEffect() is not None  # fondu en cours
    QTest.qWait(800)
    assert premiere.graphicsEffect() is None  # effet retiré une fois apparu : texte net


def test_courbe_qui_se_dessine(app):
    graphique = Graphique()
    entrees = [{"date": "2026-10-01T09:00:00", "score": 60}, {"date": "2026-10-02T09:00:00", "score": 70}]
    graphique.afficher(entrees)
    assert graphique.progres < 1
    QTest.qWait(900)
    assert graphique.progres == 1
    graphique.afficher(entrees)  # même historique : pas de nouveau tracé
    assert graphique.progres == 1


def test_bouton_copier_confirme(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch)
    fenetre.afficher(analyse_faite(tmp_path))
    fenetre.copier.click()
    assert fenetre.copier.text().strip() == "Rapport copié"
    QTest.qWait(1800)
    assert fenetre.copier.text().strip() == "Copier le rapport"


def test_molette_qui_glisse(fenetre, tmp_path, monkeypatch):
    faux_modules(monkeypatch)
    fenetre.afficher(analyse_faite(tmp_path))
    fenetre.show()
    QTest.qWait(10)
    zone = fenetre.pages.currentWidget()
    barre = zone.verticalScrollBar()
    cran = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    zone.wheelEvent(cran)
    zone.wheelEvent(cran)  # deux crans rapides s'additionnent
    attendu = min(barre.maximum(), 2 * barre.singleStep() * QApplication.wheelScrollLines())
    assert zone.glissement.endValue() == attendu
    QTest.qWait(400)
    assert barre.value() == attendu


def test_pages_opaques_pour_un_defilement_fluide(fenetre):
    """Une page opaque permet à Qt de décaler l'image au défilement au lieu de tout redessiner (60 images/s
    en plein écran). Une règle `background` de la feuille de style retirerait cet attribut sans prévenir."""
    fenetre.show()
    QTest.qWait(10)
    for numero in range(fenetre.pages.count()):
        page = fenetre.pages.widget(numero).widget()
        page.ensurePolished()
        assert page.testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)


def test_barre_en_verre_au_defilement(fenetre, tmp_path, monkeypatch):
    """Page en haut : barre fondue dans le fond. Page défilée : le contenu passé dessous s'y voit, flouté."""
    faux_modules(monkeypatch)
    fenetre.afficher(analyse_faite(tmp_path), animer=False)
    fenetre.show()
    QTest.qWait(10)
    barre = fenetre.pages.currentWidget().verticalScrollBar()
    assert fenetre.barre.flou is None and fenetre.barre.verre == 0
    barre.setValue(200)
    assert fenetre.barre.verre == 1 and fenetre.barre.flou is not None
    assert fenetre.barre.flou.height() == round(fenetre.barre.height() * fenetre.barre.ECHELLE)
    barre.setValue(0)
    assert fenetre.barre.flou is None and not fenetre.barre.relecture.isActive()


def test_echelle_typographique(app):
    from ui import theme
    assert app.font().family() == theme.famille(theme.CORPS)  # Segoe UI Variable Text, ou Segoe UI à défaut
    assert theme.police("titre").family() == theme.famille(theme.TITRE)
    assert theme.police("chiffres").featureValue(QFont.Tag("tnum")) == 1  # chiffres de même largeur
    assert theme.police("score").pointSizeF() > theme.police("titre").pointSizeF() > theme.police("corps").pointSizeF()


def test_la_lueur_suit_la_sante_du_pc(fenetre, tmp_path, monkeypatch):
    assert fenetre.ambiance.teinte == "neutre"  # avant toute analyse
    faux_modules(monkeypatch)
    fenetre.afficher(analyse_faite(tmp_path))
    assert fenetre.ambiance.teinte == "vert"
    faux_modules(monkeypatch, demarrage=plante)
    fenetre.afficher(analyse_faite(tmp_path))
    assert fenetre.ambiance.teinte == "neutre"  # analyse incomplète : pas de couleur d'état


def test_annonce(fenetre):
    fenetre.annonce.montrer("Rapport enregistré.", "valide", duree=100)
    assert fenetre.annonce.texte() == "Rapport enregistré." and not fenetre.annonce.isHidden()
    QTest.qWait(500)
    assert fenetre.annonce.isHidden()  # s'efface seule
    assert fenetre.annonce.texte() == "Rapport enregistré."  # le dernier message reste lisible


def test_feuille_de_confirmation(fenetre):
    destructive = Feuille(fenetre, "Effacer ?", "Texte", "Détails", confirmer="Effacer", destructif=True)
    assert destructive.bouton_defaut() is destructive.bouton_annuler  # Entrée n'efface jamais
    assert destructive.windowTitle() == "Effacer ?" and destructive.details() == "Détails"
    simple = Feuille(fenetre, "Info", "Texte", confirmer="OK", annuler=None)
    assert simple.bouton_annuler is None and simple.bouton_defaut() is simple.bouton_confirmer


@pytest.mark.parametrize("reponse, efface", [(QDialog.DialogCode.Accepted, True), (QDialog.DialogCode.Rejected, False)])
def test_effacer_l_historique(fenetre, tmp_path, monkeypatch, reponse, efface):
    faux_modules(monkeypatch)
    resultat = analyse.analyser()
    historique.enregistrer(resultat)  # dans le LOCALAPPDATA du test
    monkeypatch.setattr(fenetre_module.Feuille, "exec", lambda _feuille: reponse)
    fenetre.effacer_historique()
    assert (historique.charger() == []) is efface
    assert (fenetre.annonce.texte() == "Historique effacé.") is efface


def test_onglets_a_segments(fenetre):
    fenetre.show()
    QTest.qWait(10)
    segments = fenetre.onglets
    segments.groupe.button(1).click()
    assert fenetre.pages.currentIndex() == 1
    assert segments.glissement.endValue() == QRectF(segments.groupe.button(1).geometry())  # la pastille glisse
    QTest.qWait(400)
    assert segments.curseur == QRectF(segments.groupe.button(1).geometry())

