"""Fenêtre principale de Bilan santé PC (PySide6)."""

import html
import logging
import sys

from PySide6.QtCore import QStandardPaths, QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget)

import config
import historique
from modules import fichiers
from modules.disque import taille_lisible
from ui import analyse, theme
from ui.widgets import (Carte, CarteConseil, Graphique, Jauge, PastilleIcone, pastille, repolir,
                        titre_section)

journal = logging.getLogger(__name__)

# Colonnes du détail dépliable de chaque carte (les cartes sans colonnes n'ont pas de détail).
COLONNES = {"demarrage": ["Programme", "Éditeur", "Chemin"], "disque": ["Élément", "Taille", "Détail"],
            "fichiers": [], "ressources": ["Programme", "Mémoire"], "redemarrage": [], "batterie": []}

# Mot court affiché au-dessus de la phrase d'interprétation (la couleur n'est jamais seule).
ETATS = {"vert": "Bon état", "orange": "À surveiller", "rouge": "À améliorer", "gris": "Analyse incomplète"}


class Analyse(QThread):
    """Lance l'analyse hors du thread de l'interface pour que la fenêtre ne gèle pas."""

    termine = Signal(object)

    def run(self) -> None:
        resultat = analyse.analyser()
        try:  # l'historique est un plus : s'il échoue, l'analyse s'affiche quand même
            resultat["historique"] = historique.enregistrer(resultat)
            resultat["comparaison"] = historique.comparer(resultat["historique"], analyse.NOMS)
        except Exception:
            journal.exception("Échec de l'historique")
            resultat["historique"] = None
        self.termine.emit(resultat)


def carte_vide(marges: tuple[int, int, int, int] = (22, 18, 22, 18)) -> tuple[QFrame, QVBoxLayout]:
    cadre = QFrame(objectName="carte")
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
        self.setWindowIcon(theme.icone("logo", theme.ACCENT_CLAIR, 32))
        self.resize(980, 760)
        self.setMinimumSize(760, 560)
        self.resultat: dict | None = None
        self.analyse: Analyse | None = None

        contenu = QWidget(objectName="contenu")
        disposition = QVBoxLayout(contenu)
        disposition.setContentsMargins(32, 26, 32, 26)
        disposition.setSpacing(16)
        disposition.addLayout(self._entete())
        disposition.addWidget(self._heros())
        disposition.addWidget(self._historique())
        disposition.addSpacing(6)
        disposition.addWidget(titre_section("Détail par partie"))
        disposition.addLayout(self._cartes())
        disposition.addSpacing(6)
        disposition.addWidget(titre_section("Conseils"))
        disposition.addLayout(self._conseils())
        disposition.addLayout(self._actions())
        disposition.addStretch()

        defilement = QScrollArea(widgetResizable=True, frameShape=QFrame.Shape.NoFrame)
        defilement.setWidget(contenu)
        self.setCentralWidget(defilement)
        self.statusBar().showMessage("Prêt")
        self.afficher_historique_existant()

    # --- Construction des zones de la fenêtre ---

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
        entete = QHBoxLayout()
        entete.setSpacing(14)
        entete.addWidget(PastilleIcone("logo", taille=46))
        entete.addLayout(textes, 1)
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
        self.progression = QProgressBar(textVisible=False, maximum=0)  # maximum=0 : indéterminée
        self.progression.hide()

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

    def _remplacer_conseils(self, conseils: list[str], message: str = "") -> None:
        while self.liste_conseils.count():
            ancien = self.liste_conseils.takeAt(0).widget()
            ancien.hide()  # caché tout de suite : la suppression n'a lieu qu'au prochain tour de Qt
            ancien.deleteLater()
        for numero, conseil in enumerate(conseils, start=1):
            self.liste_conseils.addWidget(CarteConseil(numero, conseil))
        if message:
            cadre, disposition = carte_vide((20, 16, 20, 16))
            disposition.addWidget(QLabel(message, objectName="secondaire", wordWrap=True))
            self.liste_conseils.addWidget(cadre)

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
        self.copier.setEnabled(False)
        self.enregistrer.setEnabled(False)
        self.vider.setEnabled(False)
        self.progression.show()
        self.statusBar().showMessage("Analyse en cours... (la mesure des dossiers peut prendre une minute)")
        self.analyse = Analyse()
        self.analyse.termine.connect(self.afficher)
        self.analyse.start()

    def afficher(self, resultat: dict) -> None:
        self.resultat = resultat
        note = analyse.score_global(resultat)
        niveau, phrase = analyse.interpretation(note)
        self.jauge.definir(note, theme.NIVEAUX[niveau])
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
                          lignes_detail(cle, module) if module else [], resultat["erreurs"].get(cle))

        module_fichiers = resultat["modules"].get("fichiers")
        self.vider.setEnabled(bool(module_fichiers and module_fichiers["corbeille"]))

        conseils = analyse.conseils(resultat)
        if bilan is None:
            self._remplacer_conseils([], resultat["erreurs"]["score"])
        elif conseils:
            self._remplacer_conseils(conseils)
        elif note is None:  # pas de conseil, mais une partie n'a pas pu être vérifiée
            self._remplacer_conseils([], "Aucun conseil pour les parties vérifiées, mais l'analyse est incomplète.")
        else:
            self._remplacer_conseils([], "Rien à signaler : ton PC est en bonne forme.")

        if resultat["historique"] is None:
            self._texte_comparaison([f"L'historique n'a pas pu être lu ou enregistré. {analyse.AIDE}"])
        elif note is None:
            self._texte_comparaison(["Analyse incomplète : elle n'est pas enregistrée dans l'historique."])
            self.graphique.afficher(historique.serie(resultat["historique"]))
        else:
            self._texte_comparaison(resultat["comparaison"])
            self.graphique.afficher(historique.serie(resultat["historique"]))

        self.progression.hide()
        self.bouton.setText("  Relancer l'analyse")
        self.bouton.setEnabled(True)
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
            module = fichiers.scan()
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

    def copier_rapport(self) -> None:
        if self.resultat:
            QGuiApplication.clipboard().setText(analyse.rapport_texte(self.resultat))
            self.statusBar().showMessage("Rapport copié dans le presse-papiers.", 4000)

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
        # Fermer pendant l'analyse : on cache la fenêtre puis on attend la fin du thread,
        # sinon Qt plante en détruisant un thread encore actif.
        if self.analyse and self.analyse.isRunning():
            self.hide()
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


def preparer_application(app: QApplication) -> None:
    """Thème sombre : style Fusion, palette, police et feuille de style."""
    app.setStyle("Fusion")
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)  # barre de titre Windows sombre
    palette = QPalette()
    for role, couleur in ((QPalette.ColorRole.Window, theme.SURFACE), (QPalette.ColorRole.WindowText, theme.TEXTE),
                          (QPalette.ColorRole.Base, theme.SURFACE_2), (QPalette.ColorRole.Text, theme.TEXTE),
                          (QPalette.ColorRole.Button, theme.SURFACE_2), (QPalette.ColorRole.ButtonText, theme.TEXTE),
                          (QPalette.ColorRole.ToolTipBase, theme.SURFACE_2), (QPalette.ColorRole.ToolTipText, theme.TEXTE),
                          (QPalette.ColorRole.Highlight, theme.ACCENT), (QPalette.ColorRole.HighlightedText, "white")):
        palette.setColor(role, QColor(couleur))
    app.setPalette(palette)
    app.setFont(theme.police(10))
    app.setStyleSheet(theme.STYLE)


def lancer_interface() -> int:
    app = QApplication(sys.argv)
    preparer_application(app)
    fenetre = Fenetre()
    fenetre.show()
    journal.info("Fenêtre ouverte")
    return app.exec()
