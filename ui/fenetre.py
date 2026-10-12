"""Fenêtre principale de Bilan santé PC (PySide6)."""

import logging
import sys
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, QStandardPaths, QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMainWindow,
                               QMessageBox, QProgressBar, QPushButton, QScrollArea, QToolTip, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

import config
import historique
from modules.disque import taille_lisible
from ui import analyse

# Colonnes du détail dépliable de chaque carte (la batterie n'a pas de détail).
COLONNES = {"demarrage": ["Programme", "Éditeur", "Chemin"], "disque": ["Élément", "Taille", "Détail"],
            "ressources": ["Programme", "Mémoire"], "batterie": []}

COULEURS = {"vert": "#4caf50", "orange": "#ff9800", "rouge": "#f44336", "gris": "#9e9e9e"}

STYLE = """
QWidget { background: #1e1f22; color: #e6e6e6; }
QLabel#sous-titre { color: #9aa0a6; }
QFrame#carte { background: #2b2d31; border-radius: 10px; }
QFrame#carte QLabel, QFrame#carte QPushButton#lien { background: transparent; }
QPushButton { background: #3a3d42; border: none; border-radius: 6px; padding: 8px 16px; }
QPushButton:hover { background: #4a4e54; }
QPushButton:disabled { color: #777; background: #2b2d31; }
QPushButton#principal { background: #3d7eff; font-size: 13pt; font-weight: bold; padding: 12px 32px; }
QPushButton#principal:hover { background: #5a92ff; }
QPushButton#principal:disabled { background: #2d4a80; }
QPushButton#lien { color: #8ab4f8; text-align: left; padding: 2px 0; }
QTreeWidget { background: #232428; border: none; }
QHeaderView::section { background: #2b2d31; color: #9aa0a6; border: none; padding: 4px; }
QProgressBar { border: none; background: #2b2d31; max-height: 6px; border-radius: 3px; }
QProgressBar::chunk { background: #3d7eff; }
QScrollBar { background: #232428; width: 10px; height: 10px; }
QScrollBar::handle { background: #4a4e54; border-radius: 5px; min-height: 20px; min-width: 20px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
"""


class Analyse(QThread):
    """Lance l'analyse hors du thread de l'interface pour que la fenêtre ne gèle pas."""

    termine = Signal(object)

    def run(self) -> None:
        resultat = analyse.analyser()
        try:  # l'historique est un plus : s'il échoue, l'analyse s'affiche quand même
            resultat["historique"] = historique.enregistrer(resultat)
            resultat["comparaison"] = historique.comparer(resultat["historique"], analyse.NOMS)
        except Exception:
            logging.getLogger(__name__).exception("Échec de l'historique")
            resultat["historique"] = None
        self.termine.emit(resultat)


class Graphique(QWidget):
    """Mini-graphique de l'évolution du score (une seule série : pas de légende)."""

    MARGE = 28

    def __init__(self) -> None:
        super().__init__(minimumHeight=110, mouseTracking=True)
        self.entrees: list[dict] = []

    def afficher(self, entrees: list[dict]) -> None:
        self.entrees = entrees
        scores = ", ".join(str(e["score"]) for e in entrees)
        self.setAccessibleDescription(f"Évolution du score sur les dernières analyses : {scores}")
        self.update()

    def _positions(self) -> list[QPointF]:
        largeur, hauteur = self.width() - 2 * self.MARGE, self.height() - 20
        pas = largeur / max(1, len(self.entrees) - 1)
        return [QPointF(self.MARGE + i * pas, 10 + hauteur * (1 - e["score"] / 100))
                for i, e in enumerate(self.entrees)]

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        if len(self.entrees) < 2:
            peintre.setPen(QColor("#9aa0a6"))
            peintre.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Le graphique apparaîtra après deux analyses.")
            return
        # Repères discrets à 0, 50 et 100.
        hauteur = self.height() - 20
        peintre.setFont(QFont("Segoe UI", 8))
        for valeur in (0, 50, 100):
            y = 10 + hauteur * (1 - valeur / 100)
            peintre.setPen(QPen(QColor("#3a3d42"), 1))
            peintre.drawLine(QPointF(self.MARGE, y), QPointF(self.width() - self.MARGE, y))
            peintre.setPen(QColor("#9aa0a6"))
            peintre.drawText(QRectF(0, y - 8, self.MARGE - 6, 16),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(valeur))
        points = self._positions()
        peintre.setPen(QPen(QColor("#3d7eff"), 2))
        peintre.drawPolyline(points)
        peintre.setPen(QPen(QColor("#2b2d31"), 2))  # anneau couleur du fond autour des points
        peintre.setBrush(QColor("#3d7eff"))
        for point in points:
            peintre.drawEllipse(point, 4, 4)
        # Seule la dernière valeur est écrite, dans la couleur du texte.
        peintre.setPen(QColor("#e6e6e6"))
        dernier = points[-1]
        peintre.drawText(QRectF(dernier.x() - 20, dernier.y() - 22, 40, 14), Qt.AlignmentFlag.AlignCenter,
                         str(self.entrees[-1]["score"]))

    def mouseMoveEvent(self, evenement) -> None:
        points = self._positions()
        if len(points) < 2:
            return
        # Zone de survol plus large que le point : le plus proche horizontalement.
        index = min(range(len(points)), key=lambda i: abs(points[i].x() - evenement.position().x()))
        date = datetime.fromisoformat(self.entrees[index]["date"])
        QToolTip.showText(evenement.globalPosition().toPoint(),
                          f"{date:%d/%m/%Y %H:%M} : {self.entrees[index]['score']} / 100", self)


class Carte(QFrame):
    """Carte d'un module : score partiel, résumé et détail dépliable."""

    def __init__(self, titre: str, colonnes: list[str]) -> None:
        super().__init__(objectName="carte")
        self.titre = titre
        self.entete = QLabel(titre, font=QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.resume = QLabel("Pas encore analysé.", wordWrap=True)
        self.bouton = QPushButton("Voir le détail ▸", objectName="lien", cursor=Qt.CursorShape.PointingHandCursor)
        self.bouton.clicked.connect(self.basculer)
        self.bouton.hide()
        self.detail = QTreeWidget(rootIsDecorated=False, minimumHeight=180)
        self.detail.setHeaderLabels(colonnes)
        self.detail.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.detail.hide()
        disposition = QVBoxLayout(self)
        for widget in (self.entete, self.resume, self.bouton, self.detail):
            disposition.addWidget(widget)

    def basculer(self) -> None:
        visible = not self.detail.isVisible()
        self.detail.setVisible(visible)
        self.bouton.setText("Masquer le détail ▾" if visible else "Voir le détail ▸")

    def remplir(self, points: str, constats: list[str], lignes: list[list[str]], erreur: str | None) -> None:
        self.entete.setText(f"{self.titre} : {points}")
        self.resume.setText(erreur or "\n".join(constats))
        self.detail.clear()
        self.detail.addTopLevelItems([QTreeWidgetItem(ligne) for ligne in lignes])
        self.bouton.setVisible(bool(lignes))
        if not lignes:
            self.detail.hide()


class Fenetre(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Bilan santé PC")
        self.resize(900, 650)
        self.resultat: dict | None = None
        self.analyse: Analyse | None = None

        titre = QLabel(f"Bilan santé PC  <span style='font-size:10pt; color:#9aa0a6'>v{config.VERSION}</span>",
                       font=QFont("Segoe UI", 18, QFont.Weight.Bold))
        rassurant = QLabel("Tout reste sur ton PC. L'application ne modifie rien.", objectName="sous-titre")

        self.score = QLabel("– / 100", alignment=Qt.AlignmentFlag.AlignCenter,
                            font=QFont("Segoe UI", 44, QFont.Weight.Bold))
        self.phrase = QLabel("Clique sur « Analyser mon PC » pour commencer.",
                             alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)
        self.bouton = QPushButton("Analyser mon PC", objectName="principal",
                                  cursor=Qt.CursorShape.PointingHandCursor)
        self.bouton.clicked.connect(self.lancer)
        self.progression = QProgressBar(textVisible=False, maximum=0)  # maximum=0 : indéterminée
        self.progression.hide()

        self.cartes = {cle: Carte(nom, COLONNES[cle]) for cle, nom, _ in analyse.MODULES}
        self.cartes["batterie"].hide()  # affichée seulement si une batterie est détectée
        cartes = QGridLayout()
        for position, carte in enumerate(self.cartes.values()):
            cartes.addWidget(carte, position // 2, position % 2, Qt.AlignmentFlag.AlignTop)
        cartes.setColumnStretch(0, 1)
        cartes.setColumnStretch(1, 1)

        self.conseils = QLabel(wordWrap=True, textFormat=Qt.TextFormat.PlainText)
        cadre_conseils = QFrame(objectName="carte")
        disposition_conseils = QVBoxLayout(cadre_conseils)
        disposition_conseils.addWidget(QLabel("Conseils", font=QFont("Segoe UI", 13, QFont.Weight.Bold)))
        disposition_conseils.addWidget(self.conseils)
        self.conseils.setText("Les conseils s'afficheront après l'analyse.")

        self.copier = QPushButton("Copier le rapport", enabled=False)
        self.copier.clicked.connect(self.copier_rapport)
        self.enregistrer = QPushButton("Enregistrer le rapport", enabled=False)
        self.enregistrer.clicked.connect(self.enregistrer_rapport)
        boutons = QHBoxLayout()
        boutons.addStretch()
        boutons.addWidget(self.copier)
        boutons.addWidget(self.enregistrer)

        self.comparaison = QLabel(wordWrap=True, textFormat=Qt.TextFormat.PlainText)
        self.graphique = Graphique()
        effacer = QPushButton("Effacer l'historique")
        effacer.clicked.connect(self.effacer_historique)
        cadre_historique = QFrame(objectName="carte")
        disposition_historique = QVBoxLayout(cadre_historique)
        disposition_historique.addWidget(QLabel("Depuis la dernière fois",
                                                font=QFont("Segoe UI", 13, QFont.Weight.Bold)))
        disposition_historique.addWidget(self.comparaison)
        disposition_historique.addWidget(self.graphique)
        disposition_historique.addWidget(effacer, alignment=Qt.AlignmentFlag.AlignRight)
        self.afficher_historique_existant()

        contenu = QWidget()
        disposition = QVBoxLayout(contenu)
        disposition.setContentsMargins(24, 16, 24, 16)
        disposition.setSpacing(12)
        disposition.addWidget(titre)
        disposition.addWidget(rassurant)
        disposition.addWidget(self.score)
        disposition.addWidget(self.phrase)
        disposition.addWidget(self.bouton, alignment=Qt.AlignmentFlag.AlignCenter)
        disposition.addWidget(self.progression)
        disposition.addWidget(cadre_historique)
        disposition.addLayout(cartes)
        disposition.addWidget(cadre_conseils)
        disposition.addLayout(boutons)
        disposition.addStretch()

        defilement = QScrollArea(widgetResizable=True, frameShape=QFrame.Shape.NoFrame)
        defilement.setWidget(contenu)
        self.setCentralWidget(defilement)
        self.statusBar().showMessage("Prêt")

    def lancer(self) -> None:
        self.bouton.setEnabled(False)
        self.copier.setEnabled(False)
        self.enregistrer.setEnabled(False)
        self.progression.show()
        self.statusBar().showMessage("Analyse en cours... (la mesure des dossiers peut prendre une minute)")
        self.analyse = Analyse()
        self.analyse.termine.connect(self.afficher)
        self.analyse.start()

    def afficher(self, resultat: dict) -> None:
        self.resultat = resultat
        note = analyse.score_global(resultat)
        niveau, phrase = analyse.interpretation(note)
        self.score.setText(f"{note if note is not None else '?'} / 100")
        self.score.setStyleSheet(f"color: {COULEURS[niveau]};")
        self.phrase.setText(phrase)

        for cle, carte in self.cartes.items():
            carte.setVisible(cle in resultat["modules"])
            if cle in resultat["modules"]:
                module = resultat["modules"][cle]
                carte.remplir(analyse.points_module(resultat, cle), module["constats"] if module else [],
                              lignes_detail(cle, module) if module else [], resultat["erreurs"].get(cle))

        conseils = analyse.conseils(resultat)
        if resultat["bilan"] is None:
            texte = resultat["erreurs"]["score"]
        elif conseils:
            texte = "\n\n".join(f"{numero}. {conseil}" for numero, conseil in enumerate(conseils, start=1))
        elif note is None:  # pas de conseil, mais une partie n'a pas pu être vérifiée
            texte = "Aucun conseil pour les parties vérifiées, mais l'analyse est incomplète."
        else:
            texte = "Rien à signaler : ton PC est en bonne forme."
        self.conseils.setText(texte)

        if resultat["historique"] is None:
            self.comparaison.setText(f"L'historique n'a pas pu être lu ou enregistré. {analyse.AIDE}")
        elif note is None:
            self.comparaison.setText("Analyse incomplète : elle n'est pas enregistrée dans l'historique.")
            self.graphique.afficher(historique.serie(resultat["historique"]))
        else:
            self.comparaison.setText("\n".join(resultat["comparaison"]))
            self.graphique.afficher(historique.serie(resultat["historique"]))

        self.progression.hide()
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
            logging.getLogger(__name__).exception("Historique illisible au lancement")
            entrees = []
        self.comparaison.setText("Lance une analyse pour voir ce qui a changé depuis la dernière fois."
                                 if entrees else "Aucune analyse enregistrée pour l'instant.")

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
            logging.getLogger(__name__).exception("Impossible d'effacer l'historique")
            self.statusBar().showMessage("L'historique n'a pas pu être effacé.", 6000)
            return
        self.graphique.afficher([])
        self.comparaison.setText("Historique effacé.")
        self.statusBar().showMessage("Historique effacé.", 4000)

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
            logging.getLogger(__name__).exception("Impossible d'enregistrer le rapport")
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


def lancer_interface() -> int:
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    fenetre = Fenetre()
    fenetre.show()
    logging.getLogger(__name__).info("Fenêtre ouverte")
    return app.exec()
