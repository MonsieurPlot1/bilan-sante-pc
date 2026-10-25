"""Fenêtre principale de Bilan santé PC (PySide6)."""

import ctypes
import html
import importlib
import logging
import os
import sys
from ctypes import wintypes
from functools import cache

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QStandardPaths, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPalette
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QMainWindow, QProgressBar, QStackedWidget, QVBoxLayout, QWidget)

import historique
from modules import fichiers
from modules.disque import taille_lisible
from ui import analyse, theme
from ui.stockage import PageStockage
from ui.verre import Ambiance, Page, Verre
from ui.widgets import (Annonce, BarreHaut, Carte, CarteConseil, DefilementDoux, Feuille, Fondu, Graphique, Jauge, Logo,
                        Segmente, apparaitre, bouton, melange, pastille, pied_de_page, repolir, titre_section)

journal = logging.getLogger(__name__)

# Colonnes du détail dépliable de chaque carte (les cartes sans colonnes n'ont pas de détail).
COLONNES = {"demarrage": ["Programme", "Éditeur", "Chemin"], "disque": ["Élément", "Taille", "Détail"],
            "fichiers": [], "ressources": ["Programme", "Mémoire"], "redemarrage": [], "alimentation": [],
            "batterie": []}

DUREE_FONDU = 300  # millisecondes : passage en douceur entre le mode clair et le mode sombre
DUREE_ONGLET = 180  # millisecondes : passage en douceur d'un onglet à l'autre
ONGLETS = ["Bilan de santé", "Stockage"]
ONGLET_STOCKAGE = 1
DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # boutons de la barre de titre sombres
DWMWA_BORDER_COLOR, DWMWA_CAPTION_COLOR, DWMWA_TEXT_COLOR = 34, 35, 36  # Windows 11 : liseré, barre de titre
WTA_NONCLIENT, WTNCA_NODRAWCAPTION, WTNCA_NODRAWICON = 1, 0x1, 0x2  # barre de titre sans titre ni icône

# Mot court affiché au-dessus de la phrase d'interprétation (la couleur n'est jamais seule).
ETATS = {"vert": "Bon état", "orange": "À surveiller", "rouge": "À améliorer", "gris": "Analyse incomplète"}


class Analyse(QThread):
    """Lance l'analyse hors du thread de l'interface pour que la fenêtre ne gèle pas."""

    etape = Signal(int, int, str)  # numéro, total, nom de la partie en cours
    termine = Signal(object)

    def run(self) -> None:
        resultat = analyse.analyser(self.etape.emit)
        try:  # l'historique est un plus : s'il échoue, l'analyse s'affiche quand même
            resultat["historique"] = historique.enregistrer(resultat)
            resultat["comparaison"] = historique.comparer(resultat["historique"], analyse.NOMS)
        except Exception:
            journal.exception("Échec de l'historique")
            resultat["historique"] = None
        self.termine.emit(resultat)


def entete_section(titre: str, *droite: QWidget) -> QHBoxLayout:
    """Titre d'une section, avec ses éventuels boutons à droite."""
    ligne = QHBoxLayout()
    ligne.setContentsMargins(4, 10, 0, 0)
    ligne.addWidget(titre_section(titre))
    ligne.addStretch()
    for widget in droite:
        ligne.addWidget(widget)
    return ligne


class Fenetre(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Bilan santé PC")
        self.setMinimumSize(780, 580)
        ecran = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(min(1060, round(ecran.width() * 0.9)), min(800, round(ecran.height() * 0.9)))
        self.resultat: dict | None = None
        self.analyse: Analyse | None = None
        self.bilan_en_cours = False
        self.onglet = 0  # onglet affiché, gardé quand le contenu est recréé
        # Page Stockage : gardés ici, car la page est recréée au changement de mode clair/sombre.
        self.resultat_stockage: dict | None = None
        self.racine_stockage: str | None = None
        self.doublons_stockage: dict | None = None
        self.construire()
        colorer_barre_titre(self, *couleurs_cadre())  # barre de titre fondue dans la barre du haut
        epurer_barre_titre(self)

    def construire(self) -> None:
        """Crée le contenu de la fenêtre avec les couleurs du thème, et y remet les dernières analyses.

        En haut, la barre (application, onglets, mode) reste en place ; dessous, chaque onglet défile à part.
        Appelée aussi au changement de mode clair/sombre : l'ancien contenu est remplacé.
        """
        self.ambiance = Ambiance()
        self.pages = QStackedWidget()
        self.pages.addWidget(self._page_bilan())
        self.pages.addWidget(self._page_stockage())
        self.pages.setCurrentIndex(self.onglet)
        disposition = QVBoxLayout(self.ambiance)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)
        disposition.addWidget(self._barre())
        disposition.addWidget(self.pages, 1)
        self.annonce = Annonce(self.ambiance)
        self.setCentralWidget(self.ambiance)  # Qt supprime l'ancien contenu
        # Focus de départ sur le fond : le cadre de focus n'apparaît qu'en naviguant au clavier (Tab).
        self.ambiance.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.ambiance.setFocus()
        self._suivre_page()
        if self.resultat:
            self.afficher(self.resultat, animer=False)  # même analyse : l'anneau ne se re-remplit pas
        else:
            self.afficher_historique_existant()

    # --- Construction des zones de la fenêtre ---

    def _barre(self) -> BarreHaut:
        """Barre du haut : l'application à gauche, les onglets au milieu, le mode clair/sombre à droite."""
        self.barre = barre = BarreHaut()
        gauche = QWidget()
        identite = QHBoxLayout(gauche)
        identite.setContentsMargins(0, 0, 0, 0)
        identite.setSpacing(10)
        identite.addWidget(Logo(28))
        identite.addWidget(QLabel("Bilan santé PC", font=theme.police("carte")))
        identite.addStretch()

        self.onglets = Segmente(ONGLETS, self.onglet)
        self.groupe_onglets = self.onglets.groupe
        self.onglets.choisi.connect(self.changer_page)

        texte, icone = ("Passer en mode sombre", "lune") if theme.CLAIR else ("Passer en mode clair", "soleil")
        self.mode = bouton("", "rond", icone, theme.TEXTE_2, 15, toolTip=texte, accessibleName=texte)
        self.mode.clicked.connect(self.changer_mode)
        droite = QWidget()
        reglages = QHBoxLayout(droite)
        reglages.setContentsMargins(0, 0, 0, 0)
        reglages.addStretch()
        reglages.addWidget(self.mode)

        # Côtés de même largeur : les onglets restent pile au milieu de la fenêtre.
        cote = gauche.sizeHint().width()
        for widget in (gauche, droite):
            widget.setFixedWidth(cote)
        grille = QGridLayout(barre)
        grille.setContentsMargins(22, 0, 18, 0)
        grille.addWidget(gauche, 0, 0, Qt.AlignmentFlag.AlignVCenter)
        grille.addWidget(self.onglets, 0, 1, Qt.AlignmentFlag.AlignCenter)
        grille.addWidget(droite, 0, 2, Qt.AlignmentFlag.AlignVCenter)
        grille.setColumnStretch(1, 1)
        return barre

    def _suivre_page(self) -> None:
        """La barre du haut et le fond suivent le défilement de l'onglet affiché."""
        zone = self.pages.currentWidget()
        self.barre.suivre(zone)
        self.ambiance.defilement = zone

    @staticmethod
    def _defilement(contenu: QWidget) -> DefilementDoux:
        defilement = DefilementDoux(widgetResizable=True, frameShape=QFrame.Shape.NoFrame,
                                    horizontalScrollBarPolicy=Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        defilement.setWidget(contenu)
        return defilement

    def _page_stockage(self) -> DefilementDoux:
        self.stockage = PageStockage(self.ouvrir, self.resultat_stockage, self.racine_stockage,
                                     self.doublons_stockage)
        self.stockage.statut.connect(lambda texte, nature: self.annonce.montrer(texte, nature))
        self.stockage.occupee.connect(self._autoriser_mode)
        return self._defilement(self.stockage)

    def _page_bilan(self) -> DefilementDoux:
        contenu = Page()
        disposition = contenu.disposition
        disposition.addWidget(self._heros())
        # Les conseils juste sous le score : ce qu'il y a à faire se voit sans faire défiler.
        disposition.addLayout(entete_section("Conseils"))
        disposition.addLayout(self._conseils())
        disposition.addLayout(self._historique())
        disposition.addLayout(entete_section("Détail par partie"))
        disposition.addLayout(self._cartes())
        disposition.addLayout(self._actions())
        disposition.addWidget(pied_de_page())
        disposition.addStretch()
        return self._defilement(contenu)

    def _heros(self) -> Verre:
        """Zone principale : l'anneau du score, son interprétation et le bouton d'analyse."""
        self.jauge = Jauge()
        self.etat = pastille("Pas encore analysé")
        self.phrase = QLabel("Clique sur « Analyser mon PC » pour commencer.", wordWrap=True,
                             font=theme.police("titre"))
        self.info = QLabel("L'analyse prend environ une minute. Elle lit ton PC sans rien changer.",
                           objectName="secondaire", wordWrap=True)
        self.bouton = bouton("  Analyser mon PC", "principal", "analyser", "white", 15,
                             font=theme.police("fort"))
        self.bouton.clicked.connect(self.lancer)
        # Graduée en centièmes de partie : la barre glisse d'une partie à l'autre au lieu de sauter.
        self.progression = QProgressBar(textVisible=False, maximum=len(analyse.MODULES) * 100)
        self.progression.hide()
        self.glissement = QPropertyAnimation(self.progression, b"value", self.progression,
                                             duration=450, easingCurve=QEasingCurve.Type.OutCubic)

        droite = QVBoxLayout()
        droite.setSpacing(8)
        droite.addStretch()
        droite.addWidget(self.etat, alignment=Qt.AlignmentFlag.AlignLeft)
        droite.addSpacing(2)
        droite.addWidget(self.phrase)
        droite.addWidget(self.info)
        droite.addSpacing(12)
        droite.addWidget(self.bouton, alignment=Qt.AlignmentFlag.AlignLeft)
        droite.addWidget(self.progression)
        droite.addStretch()

        cadre = Verre(rayon=26)
        ligne = QHBoxLayout(cadre)
        ligne.setContentsMargins(26, 24, 32, 24)
        ligne.setSpacing(30)
        ligne.addWidget(self.jauge)
        ligne.addLayout(droite, 1)
        return cadre

    def _historique(self) -> QVBoxLayout:
        effacer = bouton(" Effacer l'historique", "discret", "effacer", theme.TEXTE_2, 13)
        effacer.clicked.connect(self.effacer_historique)
        self.comparaison = QLabel(wordWrap=True, textFormat=Qt.TextFormat.RichText, minimumWidth=260)
        self.graphique = Graphique()
        cadre = Verre()
        corps = QHBoxLayout(cadre)
        corps.setContentsMargins(22, 18, 18, 14)
        corps.setSpacing(24)
        corps.addWidget(self.comparaison, 0, Qt.AlignmentFlag.AlignTop)
        corps.addWidget(self.graphique, 1)
        section = QVBoxLayout()
        section.setSpacing(16)
        section.addLayout(entete_section("Depuis la dernière fois", effacer))
        section.addWidget(cadre)
        return section

    def _cartes(self) -> QHBoxLayout:
        """Deux colonnes indépendantes : chaque carte garde la hauteur de son contenu."""
        self.cartes = {cle: Carte(cle, nom, COLONNES[cle]) for cle, nom, _ in analyse.MODULES}
        self.cartes["batterie"].hide()  # affichée seulement si une batterie est détectée
        self.vider = bouton(" Vider la Corbeille", "", "effacer", theme.TEXTE, 13, enabled=False)
        self.vider.clicked.connect(self.vider_corbeille)
        self.cartes["fichiers"].layout().addWidget(self.vider, alignment=Qt.AlignmentFlag.AlignLeft)
        voir = bouton("Voir ce qui prend de la place", "lien", "stockage", theme.ACCENT_CLAIR, 12)
        voir.clicked.connect(lambda: self.changer_page(ONGLET_STOCKAGE))
        self.cartes["disque"].layout().addWidget(voir, alignment=Qt.AlignmentFlag.AlignLeft)
        colonnes = [QVBoxLayout(), QVBoxLayout()]
        for position, carte in enumerate(self.cartes.values()):
            colonnes[position % 2].addWidget(carte)
        ligne = QHBoxLayout()
        ligne.setSpacing(16)
        for colonne in colonnes:
            colonne.setSpacing(16)
            colonne.addStretch()
            ligne.addLayout(colonne, 1)
        return ligne

    def _conseils(self) -> QVBoxLayout:
        self.liste_conseils = QVBoxLayout()
        self.liste_conseils.setSpacing(10)
        self._remplacer_conseils([], "Les conseils s'afficheront après l'analyse.")
        return self.liste_conseils

    def _actions(self) -> QHBoxLayout:
        self.copier = bouton(" Copier le rapport", "", "copier", theme.TEXTE, 14, enabled=False)
        self.copier.clicked.connect(self.copier_rapport)
        self.enregistrer = bouton(" Enregistrer le rapport", "", "enregistrer", theme.TEXTE, 14, enabled=False)
        self.enregistrer.clicked.connect(self.enregistrer_rapport)
        ligne = QHBoxLayout()
        ligne.setContentsMargins(0, 4, 0, 0)
        ligne.setSpacing(10)
        ligne.addStretch()
        ligne.addWidget(self.copier)
        ligne.addWidget(self.enregistrer)
        return ligne

    # --- Affichage ---

    def _remplacer_conseils(self, conseils: list[str], message: str = "", liens: list | None = None,
                            animer: bool = False) -> None:
        """`animer` : les nouvelles cartes apparaissent en fondu, l'une après l'autre."""
        while self.liste_conseils.count():
            ancien = self.liste_conseils.takeAt(0).widget()
            ancien.hide()  # caché tout de suite : la suppression n'a lieu qu'au prochain tour de Qt
            ancien.deleteLater()
        for numero, (conseil, lien) in enumerate(zip(conseils, liens or [None] * len(conseils)), start=1):
            self.liste_conseils.addWidget(CarteConseil(numero, conseil, lien, self.ouvrir))
        if message:
            cadre = Verre(rayon=18)
            disposition = QVBoxLayout(cadre)
            disposition.setContentsMargins(20, 16, 20, 16)
            disposition.addWidget(QLabel(message, objectName="secondaire", wordWrap=True))
            self.liste_conseils.addWidget(cadre)
        if animer:
            for position in range(self.liste_conseils.count()):
                apparaitre(self.liste_conseils.itemAt(position).widget(), delai=position * 90)

    def _texte_comparaison(self, lignes: list[str]) -> None:
        """Une vraie comparaison : le score mis en avant, le reste plus discret. Un message seul : texte simple."""
        lignes = [html.escape(ligne) for ligne in lignes]
        if len(lignes) < 2:
            self.comparaison.setText(f"<span style='color:{theme.TEXTE_2}'>{''.join(lignes)}</span>")
            return
        tete, *reste = lignes
        detail = f"color:{theme.TEXTE_2}; line-height:150%; margin-top:6px"
        self.comparaison.setText(f"<div style='font-size:13.5pt; font-weight:700'>{tete}</div>"
                                 f"<div style='{detail}'>{'<br>'.join(reste)}</div>")

    def lancer(self) -> None:
        self.bouton.setEnabled(False)
        self.bouton.setText("  Analyse en cours…")
        self.phrase.setText("Analyse de ton PC en cours…")
        self.bilan_en_cours = True
        self._autoriser_mode()
        self.copier.setEnabled(False)
        self.enregistrer.setEnabled(False)
        self.vider.setEnabled(False)
        self.glissement.stop()
        self.progression.setValue(0)
        self.progression.show()
        self.info.setText("Analyse en cours… (la mesure des dossiers peut prendre une minute)")
        self.analyse = Analyse()
        self.analyse.etape.connect(self.avancer)
        self.analyse.termine.connect(self.afficher)
        self.analyse.start()

    def avancer(self, numero: int, total: int, nom: str) -> None:
        """Pendant l'analyse : la partie en cours et les parties déjà faites."""
        self.progression.setMaximum(total * 100)
        self.glissement.stop()
        self.glissement.setEndValue((numero - 1) * 100)  # depuis la position du moment
        self.glissement.start()
        self.info.setText(f"Analyse en cours : {nom} ({numero} sur {total})…")

    def afficher(self, resultat: dict, animer: bool = True) -> None:
        self.resultat = resultat
        note = analyse.score_global(resultat)
        niveau, phrase = analyse.interpretation(note)
        # La lueur prend la couleur de l'état du PC, une fois l'anneau rempli.
        self.ambiance.definir_teinte("neutre" if note is None else niveau, animer, self.jauge.animation.duration())
        self.jauge.definir(note, theme.VIFS[niveau], animer)
        self.etat.setText(ETATS[niveau])
        self.etat.setProperty("niveau", niveau)
        repolir(self.etat)
        self.phrase.setText(phrase)
        self.info.setText(f"Analyse du {resultat['date']:%d/%m/%Y à %H:%M}, terminée en {resultat['duree']:.0f} s.")

        bilan = resultat["bilan"]
        for cle, carte in self.cartes.items():
            carte.setVisible(cle in resultat["modules"])
            if cle not in resultat["modules"]:
                continue
            module = resultat["modules"][cle]
            ratio = bilan["scores"][cle] / bilan["bareme"][cle] if bilan and cle in bilan["scores"] else None
            carte.remplir(analyse.points_module(resultat, cle), ratio, module["constats"] if module else [],
                          lignes_detail(cle, module) if module else [], resultat["erreurs"].get(cle), animer)

        module_fichiers = resultat["modules"].get("fichiers")
        self.vider.setEnabled(bool(module_fichiers and module_fichiers["corbeille"]))

        conseils = analyse.conseils(resultat)
        if bilan is None:
            self._remplacer_conseils([], resultat["erreurs"]["score"], animer=animer)
        elif conseils:
            self._remplacer_conseils(conseils, liens=bilan["liens"], animer=animer)
        elif note is None:  # pas de conseil, mais une partie n'a pas pu être vérifiée
            self._remplacer_conseils([], "Aucun conseil pour les parties vérifiées, mais l'analyse est incomplète.",
                                     animer=animer)
        else:
            self._remplacer_conseils([], "Rien à signaler : ton PC est en bonne forme.", animer=animer)

        if resultat["historique"] is None:
            self._texte_comparaison([f"L'historique n'a pas pu être lu ou enregistré. {analyse.AIDE}"])
        elif note is None:
            self._texte_comparaison(["Analyse incomplète : elle n'est pas enregistrée dans l'historique."])
            self.graphique.afficher(historique.serie(resultat["historique"]), animer)
        else:
            self._texte_comparaison(resultat["comparaison"])
            self.graphique.afficher(historique.serie(resultat["historique"]), animer)

        self.progression.hide()
        self.bouton.setText("  Relancer l'analyse")
        self.bouton.setEnabled(True)
        self.bilan_en_cours = False
        self._autoriser_mode()
        self.copier.setEnabled(True)
        self.enregistrer.setEnabled(True)

    def afficher_historique_existant(self) -> None:
        """Au lancement : le graphique des analyses précédentes, s'il y en a."""
        try:
            entrees = historique.charger()
            self.graphique.afficher(historique.serie(entrees))
        except Exception:  # un historique illisible ne doit pas empêcher l'ouverture
            journal.exception("Historique illisible au lancement")
            entrees = []
        self._texte_comparaison(["Lance une analyse pour voir ce qui a changé depuis la dernière fois."]
                                if entrees else ["Aucune analyse enregistrée pour l'instant."])

    # --- Actions ---

    def effacer_historique(self) -> None:
        feuille = Feuille(self, "Effacer l'historique ?", "Toutes les analyses enregistrées seront effacées.",
                          "Cette action est définitive.", confirmer="Effacer", destructif=True, icone="effacer")
        if feuille.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            historique.effacer()
        except OSError:
            journal.exception("Impossible d'effacer l'historique")
            self.annonce.montrer("L'historique n'a pas pu être effacé.", "erreur")
            return
        self.graphique.afficher([])
        self._texte_comparaison(["Historique effacé."])
        self.annonce.montrer("Historique effacé.", "valide")

    def vider_corbeille(self) -> None:
        """Une des deux seules actions qui modifient le PC (avec « Supprimer » de l'onglet Stockage), et
        seulement sur ce clic : Windows demande lui-même confirmation."""
        try:
            avant = fichiers.corbeille()
            fichiers.vider_corbeille(int(self.winId()))
            # Fichiers temporaires et caches inchangés : les remesurer figerait la fenêtre.
            module = fichiers.scan(self.resultat["modules"]["fichiers"])
        except Exception:
            journal.exception("Impossible de vider la Corbeille")
            self.annonce.montrer("La Corbeille n'a pas pu être vidée.", "erreur")
            return
        libere = avant - module["corbeille"]
        if libere <= 0:  # confirmation refusée
            self.annonce.montrer("La Corbeille n'a pas été vidée.")
            return
        self.resultat["modules"]["fichiers"] = module
        self.cartes["fichiers"].remplir(analyse.points_module(self.resultat, "fichiers"), None, module["constats"],
                                        [], None)
        self.vider.setEnabled(bool(module["corbeille"]))
        self.annonce.montrer(f"Corbeille vidée : {taille_lisible(libere)} libérés. "
                             "Relance l'analyse pour mettre le score à jour.", "valide", 6000)

    def _autoriser_mode(self) -> None:
        """Le changement de mode recrée tout le contenu : pas pendant une analyse, qui perdrait son affichage."""
        self.mode.setEnabled(not self.bilan_en_cours and not self.stockage.en_cours())

    def changer_page(self, numero: int) -> None:
        """Onglets : la nouvelle page apparaît en fondu rapide sur l'ancienne."""
        self.groupe_onglets.button(numero).setChecked(True)  # aussi quand on arrive par un lien
        if numero == self.pages.currentIndex():
            return
        fondu = Fondu(self, self.grab(), DUREE_ONGLET)
        self.onglet = numero
        self.pages.setCurrentIndex(numero)
        self._suivre_page()
        fondu.hide()  # l'image de la nouvelle page, sans le fondu par-dessus
        nouvelle = self.grab()
        fondu.show()
        fondu.demarrer(nouvelle)

    def changer_mode(self) -> None:
        """Bouton clair/sombre : retient le choix, puis recrée le contenu avec les nouvelles couleurs."""
        try:
            theme.enregistrer_mode(not theme.CLAIR)
        except OSError:
            journal.exception("Impossible d'enregistrer le mode d'affichage")
            self.annonce.montrer("Le mode d'affichage n'a pas pu être changé.", "erreur")
            return
        # L'image de l'affichage actuel couvre la fenêtre : la suite se prépare dessous, sans rien montrer.
        fondu = Fondu(self, self.grab(), DUREE_FONDU)
        # Hors du clic : le bouton qui vient d'être cliqué fait partie du contenu remplacé.
        QTimer.singleShot(0, lambda: self._preparer_fondu(fondu))

    def _preparer_fondu(self, fondu: Fondu) -> None:
        """Recrée le contenu avec les nouvelles couleurs, sous l'image de l'ancien."""
        anciennes = couleurs_cadre()
        positions = [self.pages.widget(numero).verticalScrollBar().value() for numero in range(self.pages.count())]
        self.resultat_stockage, self.racine_stockage = self.stockage.resultat, self.stockage.racine
        self.doublons_stockage = self.stockage.doublons
        self.stockage.arreter()  # analyse finie, mais son thread peut vivre encore un instant
        # Ancien contenu supprimé tout de suite : la nouvelle feuille de style n'a pas à le restyler.
        self.takeCentralWidget()
        importlib.reload(theme)  # les couleurs sont des constantes du module : on le relit pour les recalculer
        appliquer_couleurs(QApplication.instance())
        self.construire()
        fondu.raise_()
        # Au tour suivant de Qt (tailles calculées) : même position, image du nouvel affichage, fondu.
        QTimer.singleShot(0, lambda: self._fondre(fondu, positions, anciennes))

    def _fondre(self, fondu: Fondu, positions: list[int], anciennes: tuple[QColor, QColor, QColor]) -> None:
        """Lance le fondu ; la barre de titre et le liseré suivent le même mélange de couleurs, étape par étape."""
        for numero, position in enumerate(positions):  # chaque onglet reste au même endroit
            self.pages.widget(numero).verticalScrollBar().setValue(position)
        fondu.hide()
        nouvelle = self.grab()
        fondu.show()
        nouvelles = couleurs_cadre()
        bascule = [False]

        def avancer(progres: float) -> None:
            colorer_barre_titre(self, *(melange(nouvelle_, ancienne, progres)
                                        for nouvelle_, ancienne in zip(nouvelles, anciennes)))
            if progres >= 0.5 and not bascule[0]:  # boutons réduire/fermer : ils ne savent que basculer
                bascule[0] = True
                boutons_barre_titre(self, sombres=not theme.CLAIR)

        fondu.animation.valueChanged.connect(avancer)
        fondu.animation.finished.connect(lambda: mode_barre_titre(QApplication.instance()))  # Qt au même mode
        fondu.demarrer(nouvelle)

    def ouvrir(self, cible: str) -> None:
        """Bouton « Ouvrir » d'un conseil : la page des Paramètres, le dossier ou l'outil, sans rien modifier."""
        try:
            os.startfile(cible)  # comme un double-clic
        except OSError:
            journal.exception("Impossible d'ouvrir %s", cible)
            self.annonce.montrer("Cette page n'a pas pu s'ouvrir sur ce PC.", "erreur")

    def copier_rapport(self) -> None:
        if not self.resultat:
            return
        QGuiApplication.clipboard().setText(analyse.rapport_texte(self.resultat))
        # Confirmation sur le bouton lui-même, le temps d'un coup d'œil (même largeur : rien ne bouge autour).
        bouton_copier = self.copier
        bouton_copier.setMinimumWidth(bouton_copier.width())
        bouton_copier.setText(" Rapport copié")
        bouton_copier.setIcon(theme.icone("valide", theme.NIVEAUX["vert"]))
        QTimer.singleShot(1600, bouton_copier, lambda: (bouton_copier.setText(" Copier le rapport"),
                                                        bouton_copier.setIcon(theme.icone("copier"))))

    def enregistrer_rapport(self) -> None:
        """Écrit le rapport HTML uniquement à l'endroit choisi dans la boîte de dialogue."""
        if not self.resultat:
            return
        dossier = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        nom = f"{dossier}/bilan-sante-pc-{self.resultat['date']:%Y-%m-%d}.html"
        chemin, _ = QFileDialog.getSaveFileName(self, "Enregistrer le rapport", nom, "Page web (*.html)")
        if not chemin:
            return  # annulé : aucun fichier créé
        try:
            page = analyse.rapport_html(self.resultat)  # avant d'ouvrir : jamais de fichier vide en cas d'échec
            with open(chemin, "w", encoding="utf-8") as fichier:
                fichier.write(page)
        except Exception:
            journal.exception("Impossible d'enregistrer le rapport")
            Feuille(self, "Rapport non enregistré", "Le rapport n'a pas pu être enregistré à cet endroit.",
                    "Essaie un autre dossier.", confirmer="OK", annuler=None, icone="avertissement").exec()
            return
        self.annonce.montrer("Rapport enregistré.", "valide")

    def closeEvent(self, evenement) -> None:
        # Fermer pendant une analyse : on cache la fenêtre puis on attend la fin des threads,
        # sinon Qt plante en détruisant un thread encore actif. L'analyse du stockage s'arrête en route.
        if (self.analyse and self.analyse.isRunning()) or self.stockage.en_cours():
            self.hide()
        self.stockage.arreter()
        if self.analyse:
            self.analyse.wait()
        super().closeEvent(evenement)


def lignes_detail(cle: str, module: dict) -> list[list[str]]:
    """Lignes du détail dépliable d'une carte."""
    if cle == "demarrage":
        return [[p["nom"], p["editeur"] or "inconnu", p["chemin"]] for p in module["programmes"]]
    if cle == "disque":
        lignes = [[f"Disque {d['disque']}", taille_lisible(d["libre"]) + " libres",
                   f"{d['pourcentage']:.0f} % utilisé sur {taille_lisible(d['total'])}"] for d in module["disques"]]
        return lignes + [[d["chemin"], taille_lisible(d["taille"]), "dossier du profil"]
                         for d in module["gros_dossiers"]]
    if cle == "ressources":
        return [[p["nom"], taille_lisible(p["octets"])] for p in module["processus"]]
    return []


@cache  # chargée une fois : appelée à chaque étape du fondu
def _dwm_attribut():
    fonction = ctypes.WinDLL("dwmapi").DwmSetWindowAttribute
    fonction.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    return fonction


def couleurs_cadre() -> tuple[QColor, QColor, QColor]:
    """Fond et texte de la barre de titre, et liseré de la fenêtre, aux couleurs du mode actuel."""
    return QColor(theme.FOND), QColor(theme.TEXTE), QColor(theme.BORD_FENETRE)


def colorer_barre_titre(fenetre: QWidget, fond: QColor, texte: QColor, bord: QColor) -> None:
    """Couleurs de la barre de titre et du liseré dessinés par Windows 11 (sans effet sur Windows 10)."""
    for attribut, couleur in ((DWMWA_CAPTION_COLOR, fond), (DWMWA_TEXT_COLOR, texte), (DWMWA_BORDER_COLOR, bord)):
        colorref = wintypes.DWORD(couleur.red() | couleur.green() << 8 | couleur.blue() << 16)  # 0x00BBGGRR
        _dwm_attribut()(int(fenetre.winId()), attribut, ctypes.byref(colorref), ctypes.sizeof(colorref))


class _OptionsTheme(ctypes.Structure):
    _fields_ = [("dwFlags", wintypes.DWORD), ("dwMask", wintypes.DWORD)]


def epurer_barre_titre(fenetre: QWidget) -> None:
    """Barre de titre de Windows sans titre ni icône : la barre du haut de l'application les montre déjà.

    Elle se fond alors dans la barre du haut ; le nom reste dans la barre des tâches et pour les lecteurs d'écran.
    """
    sans = WTNCA_NODRAWCAPTION | WTNCA_NODRAWICON
    options = _OptionsTheme(sans, sans)
    ctypes.WinDLL("uxtheme").SetWindowThemeAttribute(wintypes.HWND(int(fenetre.winId())), WTA_NONCLIENT,
                                                     ctypes.byref(options), ctypes.sizeof(options))


def boutons_barre_titre(fenetre: QWidget, sombres: bool) -> None:
    """Boutons réduire/fermer en version sombre ou claire, directement auprès de Windows.

    Passer par Qt (mode_barre_titre) réappliquerait le style à toute la fenêtre : un à-coup en plein fondu.
    """
    valeur = wintypes.BOOL(sombres)
    _dwm_attribut()(int(fenetre.winId()), DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(valeur),
                    ctypes.sizeof(valeur))


def mode_barre_titre(app: QApplication) -> None:
    """Boutons de la barre de titre (réduire, fermer) clairs ou sombres comme le thème."""
    app.styleHints().setColorScheme(Qt.ColorScheme.Light if theme.CLAIR else Qt.ColorScheme.Dark)


def preparer_application(app: QApplication) -> None:
    """Style Fusion, police, palette et feuille de style du mode, et icône de l'application."""
    app.setStyle("Fusion")
    app.setFont(theme.police("corps"))
    app.setWindowIcon(QIcon(str(theme.ICONE_APPLICATION)))  # vaut pour toutes les fenêtres, dialogues compris
    appliquer_couleurs(app)


def appliquer_couleurs(app: QApplication) -> None:
    """Palette et feuille de style du mode actuel (seules à changer entre clair et sombre)."""
    palette = QPalette()
    for role, couleur in ((QPalette.ColorRole.Window, theme.FOND), (QPalette.ColorRole.WindowText, theme.TEXTE),
                          (QPalette.ColorRole.Base, theme.SURFACE), (QPalette.ColorRole.Text, theme.TEXTE),
                          (QPalette.ColorRole.Button, theme.SURFACE), (QPalette.ColorRole.ButtonText, theme.TEXTE),
                          (QPalette.ColorRole.ToolTipBase, theme.SURFACE),
                          (QPalette.ColorRole.ToolTipText, theme.TEXTE),
                          (QPalette.ColorRole.Highlight, theme.ACCENT), (QPalette.ColorRole.HighlightedText, "white"),
                          (QPalette.ColorRole.PlaceholderText, theme.TEXTE_3)):
        palette.setColor(role, QColor(couleur))
    app.setPalette(palette)
    app.setFont(theme.police("corps"))  # après un changement de mode, le module du thème est relu
    app.setStyleSheet(theme.STYLE)


def lancer_interface() -> int:
    app = QApplication(sys.argv)
    preparer_application(app)
    mode_barre_titre(app)
    fenetre = Fenetre()
    fenetre.show()
    journal.info("Fenêtre ouverte")
    return app.exec()
