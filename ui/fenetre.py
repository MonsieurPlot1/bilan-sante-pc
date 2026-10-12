"""Fenêtre principale de Bilan santé PC (PySide6)."""

import sys

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QHeaderView, QLabel, QMainWindow,
                               QProgressBar, QPushButton, QScrollArea, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

import config
from modules.disque import taille_lisible
from ui import analyse

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
        self.termine.emit(analyse.analyser())


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

        self.carte_demarrage = Carte("Démarrage", ["Programme", "Éditeur", "Chemin"])
        self.carte_disque = Carte("Disque", ["Élément", "Taille", "Détail"])
        cartes = QHBoxLayout()
        cartes.addWidget(self.carte_demarrage, 1, Qt.AlignmentFlag.AlignTop)
        cartes.addWidget(self.carte_disque, 1, Qt.AlignmentFlag.AlignTop)

        self.conseils = QLabel(wordWrap=True, textFormat=Qt.TextFormat.PlainText)
        cadre_conseils = QFrame(objectName="carte")
        disposition_conseils = QVBoxLayout(cadre_conseils)
        disposition_conseils.addWidget(QLabel("Conseils", font=QFont("Segoe UI", 13, QFont.Weight.Bold)))
        disposition_conseils.addWidget(self.conseils)
        self.conseils.setText("Les conseils s'afficheront après l'analyse.")

        self.copier = QPushButton("Copier le rapport", enabled=False)
        self.copier.clicked.connect(self.copier_rapport)

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
        disposition.addLayout(cartes)
        disposition.addWidget(cadre_conseils)
        disposition.addWidget(self.copier, alignment=Qt.AlignmentFlag.AlignRight)
        disposition.addStretch()

        defilement = QScrollArea(widgetResizable=True, frameShape=QFrame.Shape.NoFrame)
        defilement.setWidget(contenu)
        self.setCentralWidget(defilement)
        self.statusBar().showMessage("Prêt")

    def lancer(self) -> None:
        self.bouton.setEnabled(False)
        self.copier.setEnabled(False)
        self.progression.show()
        self.statusBar().showMessage("Analyse en cours... (la mesure des dossiers peut prendre une minute)")
        self.analyse = Analyse()
        self.analyse.termine.connect(self.afficher)
        self.analyse.start()

    def afficher(self, resultat: dict) -> None:
        self.resultat = resultat
        bilan, erreurs = resultat["bilan"], resultat["erreurs"]
        note = analyse.score_global(resultat)
        niveau, phrase = analyse.interpretation(note)
        self.score.setText(f"{note if note is not None else '?'} / 100")
        self.score.setStyleSheet(f"color: {COULEURS[niveau]};")
        self.phrase.setText(phrase)

        def points(cle: str, maximum: int) -> str:
            return "erreur" if cle in erreurs or not bilan else f"{bilan['scores'][cle]} / {maximum}"

        demarrage = resultat["demarrage"]
        self.carte_demarrage.remplir(
            points("demarrage", config.POINTS_DEMARRAGE), demarrage["constats"],
            [[p["nom"], p["editeur"] or "inconnu", p["chemin"]] for p in demarrage["programmes"]],
            erreurs.get("demarrage"))

        disque = resultat["disque"]
        lignes = [[f"Disque {d['disque']}", taille_lisible(d["libre"]) + " libres",
                   f"{d['pourcentage']:.0f} % utilisé sur {taille_lisible(d['total'])}"] for d in disque["disques"]]
        lignes += [[d["chemin"], taille_lisible(d["taille"]), "dossier du profil"] for d in disque["gros_dossiers"]]
        self.carte_disque.remplir(points("disque", config.POINTS_DISQUE), disque["constats"], lignes,
                                  erreurs.get("disque"))

        if bilan is None:
            texte = erreurs["score"]
        elif bilan["conseils"]:
            texte = "\n\n".join(f"{numero}. {conseil}" for numero, conseil in enumerate(bilan["conseils"], start=1))
        else:
            texte = "Rien à signaler : ton PC est en bonne forme."
        self.conseils.setText(texte)

        self.progression.hide()
        self.bouton.setEnabled(True)
        self.copier.setEnabled(True)
        self.statusBar().showMessage(f"Terminé en {resultat['duree']:.0f} s")

    def copier_rapport(self) -> None:
        if self.resultat:
            QGuiApplication.clipboard().setText(analyse.rapport_texte(self.resultat))
            self.statusBar().showMessage("Rapport copié dans le presse-papiers.", 4000)

    def closeEvent(self, evenement) -> None:
        # Fermer pendant l'analyse : on cache la fenêtre puis on attend la fin du thread,
        # sinon Qt plante en détruisant un thread encore actif.
        if self.analyse and self.analyse.isRunning():
            self.hide()
            self.analyse.wait()
        super().closeEvent(evenement)


def lancer_interface() -> int:
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    fenetre = Fenetre()
    fenetre.show()
    return app.exec()
