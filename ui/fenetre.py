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
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPalette
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

import config
import historique
from modules import fichiers
from modules.disque import taille_lisible
from ui import analyse, theme
from ui.stockage import PageStockage
from ui.widgets import (Carte, CarteConseil, DefilementDoux, Fondu, Graphique, Jauge, Logo, PastilleIcone,
                        apparaitre, pastille, repolir, titre_section)

journal = logging.getLogger(__name__)

# Colonnes du détail dépliable de chaque carte (les cartes sans colonnes n'ont pas de détail).
COLONNES = {"demarrage": ["Programme", "Éditeur", "Chemin"], "disque": ["Élément", "Taille", "Détail"],
            "fichiers": [], "ressources": ["Programme", "Mémoire"], "redemarrage": [], "alimentation": [],
            "batterie": []}

DUREE_FONDU = 300  # millisecondes : passage en douceur entre le mode clair et le mode sombre
DUREE_ONGLET = 180  # millisecondes : passage en douceur d'un onglet à l'autre
ONGLETS = [("Bilan de santé", "bilan"), ("Stockage", "stockage")]  # (texte, icône)
ONGLET_STOCKAGE = 1
DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # boutons de la barre de titre sombres
DWMWA_CAPTION_COLOR, DWMWA_TEXT_COLOR = 35, 36  # Windows 11 : fond et texte de la barre de titre

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


def carte_vide(marges: tuple[int, int, int, int] = (22, 18, 22, 18)) -> tuple[QFrame, QVBoxLayout]:
    cadre = QFrame(objectName="carte")
    cadre.setAttribute(Qt.WidgetAttribute.WA_Hover)  # bordure éclairée au survol
    disposition = QVBoxLayout(cadre)
    disposition.setContentsMargins(*marges)
    disposition.setSpacing(12)
    return cadre, disposition


def entete_carte(icone: str, titre: str) -> QHBoxLayout:
    ligne = QHBoxLayout()
    ligne.setSpacing(12)
    ligne.addWidget(PastilleIcone(icone, taille=32))
    ligne.addWidget(QLabel(titre, font=theme.police(12.5, QFont.Weight.DemiBold, titre=True)))
    ligne.addStretch()
    return ligne


class Fenetre(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Bilan santé PC")
        self.resize(980, 760)
        self.setMinimumSize(760, 560)
        self.resultat: dict | None = None
        self.analyse: Analyse | None = None
        self.bilan_en_cours = False
        self.onglet = 0  # onglet affiché, gardé quand le contenu est recréé
        # Page Stockage : gardés ici, car la page est recréée au changement de mode clair/sombre.
        self.resultat_stockage: dict | None = None
        self.racine_stockage: str | None = None
        self.statusBar().showMessage("Prêt")
        self.construire()
        colorer_barre_titre(self, QColor(theme.FOND), QColor(theme.TEXTE))  # barre de titre fondue dans le fond

    def construire(self) -> None:
        """Crée le contenu de la fenêtre avec les couleurs du thème, et y remet les dernières analyses.

        En haut, l'en-tête et les onglets restent en place ; dessous, chaque onglet défile à part.
        Appelée aussi au changement de mode clair/sombre : l'ancien contenu est remplacé.
        """
        haut = QVBoxLayout()
        haut.setContentsMargins(32, 22, 32, 8)
        haut.setSpacing(16)
        haut.addLayout(self._entete())
        haut.addWidget(self._onglets(), alignment=Qt.AlignmentFlag.AlignLeft)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._page_bilan())
        self.pages.addWidget(self._page_stockage())
        self.pages.setCurrentIndex(self.onglet)

        racine = QWidget(objectName="racine")
        disposition = QVBoxLayout(racine)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)
        disposition.addLayout(haut)
        disposition.addWidget(self.pages, 1)
        self.setCentralWidget(racine)  # Qt supprime l'ancien contenu
        if self.resultat:
            self.afficher(self.resultat, animer=False)  # même analyse : la jauge ne se re-remplit pas
        else:
            self.afficher_historique_existant()

    # --- Construction des zones de la fenêtre ---

    def _onglets(self) -> QFrame:
        cadre = QFrame(objectName="onglets")
        ligne = QHBoxLayout(cadre)
        ligne.setContentsMargins(3, 3, 3, 3)
        ligne.setSpacing(2)
        self.groupe_onglets = QButtonGroup(cadre)  # un seul onglet coché à la fois
        for numero, (texte, icone) in enumerate(ONGLETS):
            symbole = theme.icone(icone, theme.TEXTE_2, 14)
            symbole.addPixmap(theme.pixmap_icone(icone, theme.ACCENT_CLAIR, 14), QIcon.Mode.Normal, QIcon.State.On)
            bouton = QPushButton(f" {texte}", objectName="onglet", checkable=True,
                                 cursor=Qt.CursorShape.PointingHandCursor, icon=symbole)
            self.groupe_onglets.addButton(bouton, numero)
            ligne.addWidget(bouton)
        self.groupe_onglets.button(self.onglet).setChecked(True)
        self.groupe_onglets.idClicked.connect(self.changer_page)
        return cadre

    @staticmethod
    def _defilement(contenu: QWidget) -> DefilementDoux:
        defilement = DefilementDoux(widgetResizable=True, frameShape=QFrame.Shape.NoFrame)
        defilement.setWidget(contenu)
        return defilement

    def _page_stockage(self) -> DefilementDoux:
        self.stockage = PageStockage(self.ouvrir, self.resultat_stockage, self.racine_stockage)
        self.stockage.statut.connect(self.statusBar().showMessage)
        self.stockage.occupee.connect(self._autoriser_mode)
        return self._defilement(self.stockage)

    def _page_bilan(self) -> DefilementDoux:
        contenu = QWidget(objectName="contenu")
        disposition = QVBoxLayout(contenu)
        disposition.setContentsMargins(32, 10, 32, 26)
        disposition.setSpacing(16)
        disposition.addWidget(self._heros())
        # Les conseils juste sous le score : ce qu'il y a à faire se voit sans faire défiler.
        disposition.addSpacing(6)
        disposition.addWidget(titre_section("Conseils"))
        disposition.addLayout(self._conseils())
        disposition.addSpacing(6)
        disposition.addWidget(self._historique())
        disposition.addSpacing(6)
        disposition.addWidget(titre_section("Détail par partie"))
        disposition.addLayout(self._cartes())
        disposition.addLayout(self._actions())
        disposition.addStretch()
        return self._defilement(contenu)

    def _entete(self) -> QHBoxLayout:
        titre = QLabel("Bilan santé PC", font=theme.police(18, QFont.Weight.DemiBold, titre=True))
        version = QLabel(f"v{config.VERSION}", objectName="version", font=theme.police(8.5))
        ligne_titre = QHBoxLayout()
        ligne_titre.setSpacing(10)
        ligne_titre.addWidget(titre)
        ligne_titre.addWidget(version, alignment=Qt.AlignmentFlag.AlignVCenter)
        ligne_titre.addStretch()

        bouclier = QLabel()
        bouclier.setPixmap(theme.pixmap_icone("bouclier", theme.NIVEAUX["vert"], 14))
        rassurant = QLabel("Tout reste sur ton PC. L'application ne modifie rien sans ton accord.",
                           objectName="secondaire")
        ligne_rassurante = QHBoxLayout()
        ligne_rassurante.setSpacing(6)
        ligne_rassurante.addWidget(bouclier)
        ligne_rassurante.addWidget(rassurant)
        ligne_rassurante.addStretch()

        textes = QVBoxLayout()
        textes.setSpacing(2)
        textes.addLayout(ligne_titre)
        textes.addLayout(ligne_rassurante)
        # Bouton clair/sombre : propose l'autre mode.
        texte, icone = ("Mode sombre", "lune") if theme.CLAIR else ("Mode clair", "soleil")
        self.mode = QPushButton(f" {texte}", objectName="discret", cursor=Qt.CursorShape.PointingHandCursor,
                                icon=theme.icone(icone, theme.TEXTE_2, 14))
        self.mode.clicked.connect(self.changer_mode)

        entete = QHBoxLayout()
        entete.setSpacing(14)
        entete.addWidget(Logo())
        entete.addLayout(textes, 1)
        entete.addWidget(self.mode, alignment=Qt.AlignmentFlag.AlignTop)
        return entete

    def _heros(self) -> QFrame:
        """Zone principale : la jauge du score, son interprétation et le bouton d'analyse."""
        self.jauge = Jauge()
        self.etat = pastille("Pas encore analysé")
        self.phrase = QLabel("Clique sur « Analyser mon PC » pour commencer.", wordWrap=True,
                             font=theme.police(17, QFont.Weight.DemiBold, titre=True))
        self.info = QLabel("L'analyse prend environ une minute. Elle lit ton PC sans rien changer.",
                           objectName="secondaire", wordWrap=True)
        self.bouton = QPushButton("  Analyser mon PC", objectName="principal",
                                  cursor=Qt.CursorShape.PointingHandCursor,
                                  icon=theme.icone("analyser", "white", 16), font=theme.police(11.5, QFont.Weight.DemiBold))
        self.bouton.clicked.connect(self.lancer)
        # Graduée en centièmes de partie : la barre glisse d'une partie à l'autre au lieu de sauter.
        self.progression = QProgressBar(textVisible=False, maximum=len(analyse.MODULES) * 100)
        self.progression.hide()
        self.glissement = QPropertyAnimation(self.progression, b"value", self.progression,
                                             duration=450, easingCurve=QEasingCurve.Type.OutCubic)

        droite = QVBoxLayout()
        droite.setSpacing(10)
        droite.addStretch()
        droite.addWidget(self.etat, alignment=Qt.AlignmentFlag.AlignLeft)
        droite.addWidget(self.phrase)
        droite.addWidget(self.info)
        droite.addSpacing(8)
        droite.addWidget(self.bouton, alignment=Qt.AlignmentFlag.AlignLeft)
        droite.addWidget(self.progression)
        droite.addStretch()

        cadre = QFrame(objectName="heros")
        ligne = QHBoxLayout(cadre)
        ligne.setContentsMargins(28, 22, 32, 22)
        ligne.setSpacing(32)
        ligne.addWidget(self.jauge)
        ligne.addLayout(droite, 1)
        return cadre

    def _historique(self) -> QFrame:
        cadre, disposition = carte_vide()
        entete = entete_carte("historique", "Depuis la dernière fois")
        effacer = QPushButton(" Effacer l'historique", objectName="discret", cursor=Qt.CursorShape.PointingHandCursor,
                              icon=theme.icone("effacer", theme.TEXTE_2, 14))
        effacer.clicked.connect(self.effacer_historique)
        entete.addWidget(effacer)
        self.comparaison = QLabel(wordWrap=True, textFormat=Qt.TextFormat.RichText, minimumWidth=270)
        self.graphique = Graphique()
        corps = QHBoxLayout()
        corps.setSpacing(24)
        corps.addWidget(self.comparaison, 0, Qt.AlignmentFlag.AlignTop)
        corps.addWidget(self.graphique, 1)
        disposition.addLayout(entete)
        disposition.addLayout(corps)
        return cadre

    def _cartes(self) -> QHBoxLayout:
        """Deux colonnes indépendantes : chaque carte garde la hauteur de son contenu."""
        self.cartes = {cle: Carte(cle, nom, COLONNES[cle]) for cle, nom, _ in analyse.MODULES}
        self.cartes["batterie"].hide()  # affichée seulement si une batterie est détectée
        self.vider = QPushButton(" Vider la Corbeille", enabled=False, cursor=Qt.CursorShape.PointingHandCursor,
                                 icon=theme.icone("effacer", theme.TEXTE_2, 14))
        self.vider.clicked.connect(self.vider_corbeille)
        self.cartes["fichiers"].layout().addWidget(self.vider, alignment=Qt.AlignmentFlag.AlignLeft)
        voir = QPushButton("Voir ce qui prend de la place", objectName="lien", cursor=Qt.CursorShape.PointingHandCursor,
                           icon=theme.icone("stockage", theme.ACCENT_CLAIR, 12))
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
        self.copier = QPushButton(" Copier le rapport", enabled=False, icon=theme.icone("copier"),
                                  cursor=Qt.CursorShape.PointingHandCursor)
        self.copier.clicked.connect(self.copier_rapport)
        self.enregistrer = QPushButton(" Enregistrer le rapport", enabled=False, icon=theme.icone("enregistrer"),
                                       cursor=Qt.CursorShape.PointingHandCursor)
        self.enregistrer.clicked.connect(self.enregistrer_rapport)
        ligne = QHBoxLayout()
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
            cadre, disposition = carte_vide((20, 16, 20, 16))
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
        self.comparaison.setText(f"<div style='font-size:13pt; font-weight:600'>{tete}</div>"
                                 f"<div style='color:{theme.TEXTE_2}'>{'<br>'.join(reste)}</div>")

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
        self.statusBar().showMessage("Analyse en cours... (la mesure des dossiers peut prendre une minute)")
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
        self.jauge.definir(note, theme.NIVEAUX[niveau], animer)
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
        self.statusBar().showMessage(f"Terminé en {resultat['duree']:.0f} s")

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
        boite = QMessageBox(QMessageBox.Icon.Question, "Effacer l'historique",
                            "Effacer toutes les analyses enregistrées ? Cette action est définitive.", parent=self)
        confirmer = boite.addButton("Effacer", QMessageBox.ButtonRole.DestructiveRole)
        boite.setDefaultButton(boite.addButton("Annuler", QMessageBox.ButtonRole.RejectRole))
        boite.exec()
        if boite.clickedButton() is not confirmer:
            return
        try:
            historique.effacer()
        except OSError:
            journal.exception("Impossible d'effacer l'historique")
            self.statusBar().showMessage("L'historique n'a pas pu être effacé.", 6000)
            return
        self.graphique.afficher([])
        self._texte_comparaison(["Historique effacé."])
        self.statusBar().showMessage("Historique effacé.", 4000)

    def vider_corbeille(self) -> None:
        """Seule action qui modifie le PC, et seulement sur ce clic : Windows demande lui-même confirmation."""
        try:
            avant = fichiers.corbeille()
            fichiers.vider_corbeille(int(self.winId()))
            # Fichiers temporaires et caches inchangés : les remesurer figerait la fenêtre.
            module = fichiers.scan(self.resultat["modules"]["fichiers"])
        except Exception:
            journal.exception("Impossible de vider la Corbeille")
            self.statusBar().showMessage("La Corbeille n'a pas pu être vidée.", 6000)
            return
        libere = avant - module["corbeille"]
        if libere <= 0:  # confirmation refusée
            self.statusBar().showMessage("La Corbeille n'a pas été vidée.", 4000)
            return
        self.resultat["modules"]["fichiers"] = module
        self.cartes["fichiers"].remplir(analyse.points_module(self.resultat, "fichiers"), None, module["constats"],
                                        [], None)
        self.vider.setEnabled(bool(module["corbeille"]))
        self.statusBar().showMessage(f"Corbeille vidée : {taille_lisible(libere)} libérés. "
                                     "Relance l'analyse pour mettre le score à jour.")

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
            self.statusBar().showMessage("Le mode d'affichage n'a pas pu être changé.", 6000)
            return
        # L'image de l'affichage actuel couvre la fenêtre : la suite se prépare dessous, sans rien montrer.
        fondu = Fondu(self, self.grab(), DUREE_FONDU)
        # Hors du clic : le bouton qui vient d'être cliqué fait partie du contenu remplacé.
        QTimer.singleShot(0, lambda: self._preparer_fondu(fondu))

    def _preparer_fondu(self, fondu: Fondu) -> None:
        """Recrée le contenu avec les nouvelles couleurs, sous l'image de l'ancien."""
        ancien_fond, ancien_texte = QColor(theme.FOND), QColor(theme.TEXTE)
        positions = [self.pages.widget(numero).verticalScrollBar().value() for numero in range(self.pages.count())]
        self.resultat_stockage, self.racine_stockage = self.stockage.resultat, self.stockage.racine
        self.stockage.arreter()  # analyse finie, mais son thread peut vivre encore un instant
        # Ancien contenu supprimé tout de suite : la nouvelle feuille de style n'a pas à le restyler.
        self.takeCentralWidget()
        importlib.reload(theme)  # les couleurs sont des constantes du module : on le relit pour les recalculer
        appliquer_couleurs(QApplication.instance())
        self.construire()
        fondu.raise_()
        # Au tour suivant de Qt (tailles calculées) : même position, image du nouvel affichage, fondu.
        QTimer.singleShot(0, lambda: self._fondre(fondu, positions, ancien_fond, ancien_texte))

    def _fondre(self, fondu: Fondu, positions: list[int], ancien_fond: QColor, ancien_texte: QColor) -> None:
        """Lance le fondu ; la barre de titre suit le même mélange de couleurs, étape par étape."""
        for numero, position in enumerate(positions):  # chaque onglet reste au même endroit
            self.pages.widget(numero).verticalScrollBar().setValue(position)
        fondu.hide()
        nouvelle = self.grab()
        fondu.show()
        nouveau_fond, nouveau_texte = QColor(theme.FOND), QColor(theme.TEXTE)
        bascule = [False]

        def avancer(progres: float) -> None:
            colorer_barre_titre(self, melange(nouveau_fond, ancien_fond, progres),
                                melange(nouveau_texte, ancien_texte, progres))
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
            self.statusBar().showMessage("Cette page n'a pas pu s'ouvrir sur ce PC.", 6000)

    def copier_rapport(self) -> None:
        if not self.resultat:
            return
        QGuiApplication.clipboard().setText(analyse.rapport_texte(self.resultat))
        self.statusBar().showMessage("Rapport copié dans le presse-papiers.", 4000)
        # Confirmation sur le bouton lui-même, le temps d'un coup d'œil (même largeur : rien ne bouge autour).
        bouton = self.copier
        bouton.setMinimumWidth(bouton.width())
        bouton.setText(" Rapport copié")
        bouton.setIcon(theme.icone("valide", theme.NIVEAUX["vert"]))
        QTimer.singleShot(1600, bouton, lambda: (bouton.setText(" Copier le rapport"),
                                                 bouton.setIcon(theme.icone("copier"))))

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
            QMessageBox.warning(self, "Rapport non enregistré",
                                "Le rapport n'a pas pu être enregistré à cet endroit. Essaie un autre dossier.")
            return
        self.statusBar().showMessage("Rapport enregistré.", 4000)

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


def melange(a: QColor, b: QColor, part_de_a: float) -> QColor:
    """Couleur entre `b` (0) et `a` (1), comme deux images superposées en transparence."""
    return QColor(*(round(x * part_de_a + y * (1 - part_de_a))
                    for x, y in ((a.red(), b.red()), (a.green(), b.green()), (a.blue(), b.blue()))))


@cache  # chargée une fois : appelée à chaque étape du fondu
def _dwm_attribut():
    fonction = ctypes.WinDLL("dwmapi").DwmSetWindowAttribute
    fonction.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    return fonction


def colorer_barre_titre(fenetre: QWidget, fond: QColor, texte: QColor) -> None:
    """Couleurs de la barre de titre dessinée par Windows 11 (sans effet sur Windows 10)."""
    for attribut, couleur in ((DWMWA_CAPTION_COLOR, fond), (DWMWA_TEXT_COLOR, texte)):
        colorref = wintypes.DWORD(couleur.red() | couleur.green() << 8 | couleur.blue() << 16)  # 0x00BBGGRR
        _dwm_attribut()(int(fenetre.winId()), attribut, ctypes.byref(colorref), ctypes.sizeof(colorref))


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
    """Thème clair ou sombre : style Fusion, police, palette et feuille de style, et icône de l'application."""
    app.setStyle("Fusion")
    app.setFont(theme.police(10))
    app.setWindowIcon(QIcon(str(theme.ICONE_APPLICATION)))  # vaut pour toutes les fenêtres, dialogues compris
    appliquer_couleurs(app)


def appliquer_couleurs(app: QApplication) -> None:
    """Palette et feuille de style du mode actuel (seules à changer entre clair et sombre)."""
    palette = QPalette()
    for role, couleur in ((QPalette.ColorRole.Window, theme.SURFACE), (QPalette.ColorRole.WindowText, theme.TEXTE),
                          (QPalette.ColorRole.Base, theme.SURFACE_2), (QPalette.ColorRole.Text, theme.TEXTE),
                          (QPalette.ColorRole.Button, theme.SURFACE_2), (QPalette.ColorRole.ButtonText, theme.TEXTE),
                          (QPalette.ColorRole.ToolTipBase, theme.SURFACE_2), (QPalette.ColorRole.ToolTipText, theme.TEXTE),
                          (QPalette.ColorRole.Highlight, theme.ACCENT), (QPalette.ColorRole.HighlightedText, "white")):
        palette.setColor(role, QColor(couleur))
    app.setPalette(palette)
    app.setStyleSheet(theme.STYLE)


def lancer_interface() -> int:
    app = QApplication(sys.argv)
    preparer_application(app)
    mode_barre_titre(app)
    fenetre = Fenetre()
    fenetre.show()
    journal.info("Fenêtre ouverte")
    return app.exec()
