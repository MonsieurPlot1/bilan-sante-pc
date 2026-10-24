"""Page Stockage : ce qui prend de la place sur un disque, classé en 12 catégories (PySide6).

Lecture seule : les boutons « Afficher » ouvrent seulement l'Explorateur, rien n'est supprimé.
"""

import logging
import os
import subprocess
import threading
from datetime import datetime
from typing import Callable

import psutil
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QThread, QVariantAnimation, Qt, Signal
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from modules import disque, stockage
from modules.disque import taille_lisible
from ui import theme
from ui.analyse import AIDE, arriere_plan
from ui.widgets import BarreScore, PastilleIcone, apparaitre, pastille, repolir, titre_section

journal = logging.getLogger(__name__)

NB_PLUS_GROS = 8  # éléments de « Ce qui prend le plus de place »
NB_PAR_CATEGORIE = 8  # éléments montrés quand une catégorie est dépliée
HAUTEUR_LIBRE = 16777215  # QWIDGETSIZE_MAX : plus de limite de hauteur
LARGEUR_CHIFFRES = 96  # colonne taille et part du disque (« moins de 1 % »)

# Remplissage du disque : mot affiché à côté de la jauge (la couleur n'est jamais seule).
ETATS = {"vert": "Assez de place", "orange": "Bien rempli", "rouge": "Presque plein"}


class AnalyseStockage(QThread):
    """Parcourt le disque hors du thread de l'interface, en priorité basse."""

    avance = Signal(float, int)  # octets comptés (float : au-delà de 2 Go), fichiers comptés
    termine = Signal(object)  # résultat, None si l'analyse a été arrêtée, ou {"erreur": texte}

    def __init__(self, racine: str) -> None:
        super().__init__()
        self.racine = racine
        self.arret = threading.Event()

    def run(self) -> None:
        try:
            with arriere_plan():
                resultat = stockage.scan(self.racine, lambda octets, nombre: self.avance.emit(float(octets), nombre),
                                         self.arret.is_set)
        except Exception:  # n'importe quelle panne : la page l'annonce au lieu de rester bloquée
            journal.exception("Échec de l'analyse du stockage")
            resultat = {"erreur": f"L'analyse du stockage n'a pas pu aboutir. {AIDE}"}
        self.termine.emit(resultat)


def nombre_lisible(nombre: int) -> str:
    """« 584 684 » : chiffres groupés par trois, à la française."""
    return f"{nombre:,}".replace(",", "\u202f")


def part_lisible(taille: int, total: int) -> str:
    part = 100 * taille / total if total else 0
    return "moins de 1 %" if 0 < part < 1 else f"{part:.0f} %"


def niveau_remplissage(pourcentage: float) -> str:
    """Mêmes seuils que le score du disque : vert jusqu'à 70 %, rouge à partir de 90 %."""
    return "vert" if pourcentage < 70 else "orange" if pourcentage < 90 else "rouge"


class TexteCoupe(QLabel):
    """Texte sur une ligne, coupé au milieu s'il est trop long (« C:\\Users\\…\\film.mkv »), complet au survol."""

    def __init__(self, texte: str, **proprietes) -> None:
        super().__init__(texte, **proprietes)
        self.setToolTip(texte)
        self.setMinimumWidth(60)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def paintEvent(self, _evenement) -> None:
        coupe = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideMiddle, self.width())
        # Dessiné par le style : la couleur de la feuille de style (objectName) est respectée.
        alignement = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        self.style().drawItemText(QPainter(self), self.rect(), alignement, self.palette(), self.isEnabled(), coupe,
                                  self.foregroundRole())


class ListeDisques(QComboBox):
    """Liste déroulante des disques, avec sa flèche (la feuille de style retire celle de Windows)."""

    def paintEvent(self, evenement) -> None:
        super().paintEvent(evenement)
        cote = 10
        image = theme.pixmap_icone("deplier", theme.TEXTE_2, cote, self.devicePixelRatioF())
        QPainter(self).drawPixmap(self.width() - cote - 12, (self.height() - cote) // 2, image)


class LigneElement(QFrame):
    """Un dossier ou un fichier : nom, emplacement, taille, et « Afficher » pour le voir dans l'Explorateur."""

    def __init__(self, element: dict, montrer: Callable[[str, bool], None], categorie: str | None = None) -> None:
        super().__init__(objectName="ligne")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        icone = QLabel()
        icone.setPixmap(theme.pixmap_icone("dossier" if element["dossier"] else "fichier", theme.TEXTE_3, 16))
        textes = QVBoxLayout()
        textes.setSpacing(1)
        textes.addWidget(TexteCoupe(element["nom"], font=theme.police(10, QFont.Weight.DemiBold)))
        if element["chemin"]:
            textes.addWidget(TexteCoupe(element["chemin"], objectName="secondaire", font=theme.police(9)))
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(10, 7, 8, 7)
        disposition.setSpacing(12)
        disposition.addWidget(icone)
        disposition.addLayout(textes, 1)
        if categorie:
            disposition.addWidget(pastille(stockage.NOMS[categorie]))
        taille = QLabel(taille_lisible(element["taille"]), font=theme.police(10, QFont.Weight.DemiBold),
                        alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        taille.setMinimumWidth(70)
        disposition.addWidget(taille)
        if element["chemin"]:
            bouton = QPushButton("Afficher", objectName="lien", cursor=Qt.CursorShape.PointingHandCursor,
                                 icon=theme.icone("ouvrir", theme.ACCENT_CLAIR, 12),
                                 toolTip="Ouvrir son emplacement dans l'Explorateur (rien n'est modifié)")
            bouton.clicked.connect(lambda: montrer(element["chemin"], element["dossier"]))
            disposition.addWidget(bouton)


class LigneCategorie(QFrame):
    """Une catégorie : icône, nom, explication, taille et part du disque ; un clic déplie ce qu'elle contient."""

    def __init__(self, categorie: dict, utilise: int, montrer: Callable[[str, bool], None],
                 ouvrir: Callable[[str], None]) -> None:
        super().__init__(objectName="ligne")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.categorie, self.ouvert = categorie, False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # dépliable au clavier (Entrée ou Espace)
        self.setAccessibleName(f"{categorie['nom']} : {taille_lisible(categorie['taille'])}")

        nom = QLabel(categorie["nom"], font=theme.police(11, QFont.Weight.DemiBold))
        description = QLabel(categorie["description"], objectName="secondaire", wordWrap=True)
        self.barre = BarreScore()
        textes = QVBoxLayout()
        textes.setSpacing(4)
        textes.addWidget(nom)
        textes.addWidget(description)
        textes.addSpacing(2)
        textes.addWidget(self.barre)
        taille = QLabel(taille_lisible(categorie["taille"]), font=theme.police(11, QFont.Weight.DemiBold),
                        alignment=Qt.AlignmentFlag.AlignRight)
        part = QLabel(part_lisible(categorie["taille"], utilise), objectName="discret",
                      alignment=Qt.AlignmentFlag.AlignRight)
        chiffres = QVBoxLayout()
        chiffres.setSpacing(2)
        chiffres.addWidget(taille)
        chiffres.addWidget(part)
        chiffres.addStretch()
        colonne = QWidget(fixedWidth=LARGEUR_CHIFFRES)  # même largeur partout : barres comparables
        colonne.setLayout(chiffres)
        chiffres.setContentsMargins(0, 0, 0, 0)
        self.chevron = QLabel()
        self.chevron.setPixmap(theme.pixmap_icone("deplier", theme.TEXTE_3, 12))
        entete = QHBoxLayout()
        entete.setSpacing(14)
        entete.addWidget(PastilleIcone(categorie["cle"], taille=36), alignment=Qt.AlignmentFlag.AlignTop)
        entete.addLayout(textes, 1)
        entete.addWidget(colonne)
        entete.addWidget(self.chevron, alignment=Qt.AlignmentFlag.AlignTop)

        self.detail = QWidget(maximumHeight=0)
        self.detail.setCursor(Qt.CursorShape.ArrowCursor)
        contenu = QVBoxLayout(self.detail)
        contenu.setContentsMargins(46, 8, 0, 4)
        contenu.setSpacing(2)
        for element in categorie["elements"][:NB_PAR_CATEGORIE]:
            contenu.addWidget(LigneElement(element, montrer))
        if not categorie["elements"]:
            contenu.addWidget(QLabel("Rien à montrer ici.", objectName="secondaire"))
        if categorie["surtout_dans"]:
            lieux = ", ".join(f"{d['nom']} ({taille_lisible(d['taille'])})" for d in categorie["surtout_dans"])
            surtout = QLabel(f"Surtout dans : {lieux}", objectName="secondaire", wordWrap=True)
            surtout.setContentsMargins(10, 6, 0, 0)
            contenu.addWidget(surtout)
        if categorie["lien"]:
            libelle, cible = categorie["lien"]
            lien = QPushButton(libelle, objectName="lien", cursor=Qt.CursorShape.PointingHandCursor,
                               icon=theme.icone("ouvrir", theme.ACCENT_CLAIR, 12))
            lien.clicked.connect(lambda: ouvrir(cible))
            contenu.addWidget(lien, alignment=Qt.AlignmentFlag.AlignLeft)
        # Dépliage en douceur (hauteur animée), comme le détail des cartes du bilan.
        self.animation = QVariantAnimation(self, duration=220, easingCurve=QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(lambda hauteur: self.detail.setMaximumHeight(round(hauteur)))
        self.animation.finished.connect(self._fin_animation)

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(12, 12, 14, 12)
        disposition.setSpacing(0)
        disposition.addLayout(entete)
        disposition.addWidget(self.detail)

    def remplir(self, ratio: float, animer: bool) -> None:
        self.barre.definir(ratio, theme.ACCENT_CLAIR, animer)

    def basculer(self) -> None:
        self.ouvert = not self.ouvert
        self.chevron.setPixmap(theme.pixmap_icone("replier" if self.ouvert else "deplier", theme.TEXTE_3, 12))
        depart = min(self.detail.maximumHeight(), self.detail.height())  # repart d'où il en est
        largeur = self.detail.width() or self.width()
        hauteur = self.detail.heightForWidth(largeur) if self.detail.hasHeightForWidth() else -1
        cible = (hauteur if hauteur > 0 else self.detail.sizeHint().height()) if self.ouvert else 0
        self.animation.stop()
        self.animation.setStartValue(float(depart))
        self.animation.setEndValue(float(cible))
        self.animation.start()

    def _fin_animation(self) -> None:
        if self.ouvert:  # ouvert : plus de limite, le contenu peut changer de hauteur avec la fenêtre
            self.detail.setMaximumHeight(HAUTEUR_LIBRE)

    def mousePressEvent(self, evenement) -> None:
        if evenement.button() == Qt.MouseButton.LeftButton and evenement.position().y() < self.detail.y():
            self.basculer()  # clic sur l'en-tête ; un clic dans le détail n'y touche pas
        super().mousePressEvent(evenement)

    def keyPressEvent(self, evenement) -> None:
        if evenement.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.basculer()
            return
        super().keyPressEvent(evenement)


def carte(marges: tuple[int, int, int, int] = (22, 18, 22, 18)) -> tuple[QFrame, QVBoxLayout]:
    cadre = QFrame(objectName="carte")
    disposition = QVBoxLayout(cadre)
    disposition.setContentsMargins(*marges)
    disposition.setSpacing(4)
    return cadre, disposition


class PageStockage(QWidget):
    """Contenu de l'onglet Stockage. La fenêtre le place dans une zone de défilement."""

    statut = Signal(str)  # message pour la barre d'état
    occupee = Signal(bool)  # analyse en cours : la fenêtre bloque le changement de mode clair/sombre

    def __init__(self, ouvrir: Callable[[str], None], resultat: dict | None = None,
                 racine: str | None = None) -> None:
        super().__init__(objectName="contenu")
        self.ouvrir = ouvrir
        self.resultat = resultat
        # Le thread est gardé après sa fin : son signal de fin arrive un instant avant qu'il s'arrête,
        # et Qt plante s'il détruit un thread encore actif. `occupe` dit si l'analyse est en cours.
        self.analyse: AnalyseStockage | None = None
        self.occupe = False
        self.espace_utilise = 0  # au lancement de l'analyse : sert à estimer sa progression
        self.disques = disque.lister_disques()
        self.racine = racine or (resultat["racine"] if resultat else stockage.disque_systeme())

        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(32, 10, 32, 26)
        disposition.setSpacing(16)
        disposition.addWidget(self._heros())
        disposition.addSpacing(6)
        self.titre_plus_gros = titre_section("Ce qui prend le plus de place")
        self.plus_gros, self.liste_plus_gros = carte((10, 10, 10, 10))
        disposition.addWidget(self.titre_plus_gros)
        disposition.addWidget(self.plus_gros)
        disposition.addSpacing(6)
        self.titre_categories = titre_section("Par catégorie")
        self.categories, self.liste_categories = carte((10, 10, 10, 10))
        disposition.addWidget(self.titre_categories)
        disposition.addWidget(self.categories)
        disposition.addWidget(self._aide())
        disposition.addStretch()

        if resultat:
            self.afficher(resultat, animer=False)  # même analyse : rien ne se re-remplit
        else:
            self._sans_resultat(animer=False)

    # --- Construction ---

    def _heros(self) -> QFrame:
        self.etat = pastille()
        self.choix = ListeDisques(cursor=Qt.CursorShape.PointingHandCursor, accessibleName="Disque à analyser")
        for numero, d in enumerate(self.disques):
            self.choix.addItem(f"Disque {d['disque'].rstrip(os.sep)} · {taille_lisible(d['libre'])} libres",
                               d["disque"])
            if os.path.normcase(d["disque"]) == os.path.normcase(self.racine):
                self.choix.setCurrentIndex(numero)
        self.choix.setVisible(len(self.disques) > 1)
        self.choix.currentIndexChanged.connect(self.changer_disque)
        haut = QHBoxLayout()
        haut.addWidget(self.etat)
        haut.addStretch()
        haut.addWidget(self.choix)

        self.utilise = QLabel(font=theme.police(26, QFont.Weight.DemiBold, titre=True))
        self.sur = QLabel(objectName="secondaire")
        chiffres = QHBoxLayout()
        chiffres.setSpacing(10)
        chiffres.addWidget(self.utilise, alignment=Qt.AlignmentFlag.AlignBottom)
        chiffres.addWidget(self.sur, 1, alignment=Qt.AlignmentFlag.AlignBottom)
        self.jauge = BarreScore()
        self.jauge.setFixedHeight(10)
        self.info = QLabel(objectName="secondaire", wordWrap=True)

        self.bouton = QPushButton(objectName="principal", cursor=Qt.CursorShape.PointingHandCursor,
                                  icon=theme.icone("analyser", "white", 16),
                                  font=theme.police(11.5, QFont.Weight.DemiBold))
        self.bouton.clicked.connect(self.lancer)
        self.progression = QProgressBar(textVisible=False, maximum=1000)
        self.progression.hide()
        self.glissement = QPropertyAnimation(self.progression, b"value", self.progression,
                                             duration=450, easingCurve=QEasingCurve.Type.OutCubic)

        cadre = QFrame(objectName="heros")
        disposition = QVBoxLayout(cadre)
        disposition.setContentsMargins(28, 22, 28, 22)
        disposition.setSpacing(10)
        disposition.addLayout(haut)
        disposition.addLayout(chiffres)
        disposition.addWidget(self.jauge)
        disposition.addWidget(self.info)
        disposition.addSpacing(6)
        disposition.addWidget(self.bouton, alignment=Qt.AlignmentFlag.AlignLeft)
        disposition.addWidget(self.progression)
        return cadre

    def _aide(self) -> QFrame:
        cadre, disposition = carte()
        disposition.setSpacing(8)
        texte = QLabel("Pour faire de la place sans risque, commence par les fichiers temporaires et la Corbeille, "
                       "puis trie Téléchargements. Pour enlever un jeu ou un logiciel, désinstalle-le depuis les "
                       "Paramètres ou son lanceur (Steam, Epic…) : supprimer son dossier à la main laisse des "
                       "restes. Ici, rien n'est supprimé : « Afficher » ouvre seulement l'Explorateur.",
                       objectName="secondaire", wordWrap=True)
        libelle, cible = stockage.LIEN_STOCKAGE
        bouton = QPushButton(libelle, objectName="lien", cursor=Qt.CursorShape.PointingHandCursor,
                             icon=theme.icone("ouvrir", theme.ACCENT_CLAIR, 12))
        bouton.clicked.connect(lambda: self.ouvrir(cible))
        disposition.addWidget(texte)
        disposition.addWidget(bouton, alignment=Qt.AlignmentFlag.AlignLeft)
        return cadre

    # --- Affichage ---

    def _remplissage(self, utilise: int, total: int, libre: int, animer: bool) -> None:
        """En-tête : espace utilisé du disque, avec un mot et une couleur selon son remplissage."""
        pourcentage = 100 * utilise / total if total else 0
        niveau = niveau_remplissage(pourcentage)
        self.etat.setText(ETATS[niveau])
        self.etat.setProperty("niveau", niveau)
        repolir(self.etat)
        self.utilise.setText(f"{taille_lisible(utilise)} utilisés")
        self.sur.setText(f"sur {taille_lisible(total)} · {taille_lisible(libre)} libres "
                         f"({pourcentage:.0f} % utilisé)")
        self.jauge.definir(pourcentage / 100, theme.NIVEAUX[niveau], animer)

    def _sans_resultat(self, erreur: str | None = None, animer: bool = True) -> None:
        """Avant toute analyse de ce disque : son remplissage, lu tout de suite, et l'invitation à analyser."""
        self.resultat = None
        try:
            usage = psutil.disk_usage(self.racine)
            self._remplissage(usage.used, usage.total, usage.free, animer)
        except OSError:
            journal.exception("Disque %s illisible", self.racine)
        self.info.setText(erreur or "Lance l'analyse pour voir ce qui prend de la place. Elle lit les dossiers "
                                    "sans rien changer et peut prendre une ou deux minutes.")
        self.info.setObjectName("erreur" if erreur else "secondaire")
        repolir(self.info)
        self.bouton.setText("  Analyser le stockage")
        for widget in (self.titre_plus_gros, self.plus_gros, self.titre_categories, self.categories):
            widget.hide()

    def afficher(self, resultat: dict, animer: bool = True) -> None:
        self.resultat = resultat
        utilise = resultat["utilise"]
        self._remplissage(utilise, resultat["total"], resultat["libre"], animer)
        self.info.setText(f"Analyse du {resultat['date']:%d/%m/%Y à %H:%M} : "
                          f"{nombre_lisible(resultat['fichiers'])} fichiers parcourus en {resultat['duree']:.0f} s.")
        self.info.setObjectName("secondaire")
        repolir(self.info)
        self.bouton.setText("  Relancer l'analyse")

        # Ce qui prend le plus de place, toutes catégories confondues (sauf Système : rien à y faire).
        elements = sorted(((e, c["cle"]) for c in resultat["categories"] if c["cle"] != "systeme"
                           for e in c["elements"]), key=lambda paire: paire[0]["taille"], reverse=True)
        self._vider(self.liste_plus_gros)
        for position, (element, cle) in enumerate(elements[:NB_PLUS_GROS]):
            ligne = LigneElement(element, self.montrer, cle)
            self.liste_plus_gros.addWidget(ligne)
            if animer:
                apparaitre(ligne, delai=position * 40)

        self._vider(self.liste_categories)
        for categorie in sorted(resultat["categories"], key=lambda c: c["taille"], reverse=True):
            ligne = LigneCategorie(categorie, utilise, self.montrer, self.ouvrir)
            self.liste_categories.addWidget(ligne)
            ligne.remplir(categorie["taille"] / utilise if utilise else 0, animer)
        for widget in (self.titre_plus_gros, self.plus_gros, self.titre_categories, self.categories):
            widget.show()
        self.plus_gros.setVisible(bool(elements))
        self.titre_plus_gros.setVisible(bool(elements))

    @staticmethod
    def _vider(disposition: QVBoxLayout) -> None:
        while disposition.count():
            ancien = disposition.takeAt(0).widget()
            ancien.hide()  # caché tout de suite : la suppression n'a lieu qu'au prochain tour de Qt
            ancien.deleteLater()

    def lignes_categories(self) -> list[LigneCategorie]:
        return [self.liste_categories.itemAt(i).widget() for i in range(self.liste_categories.count())]

    # --- Analyse ---

    def en_cours(self) -> bool:
        return self.occupe

    def lancer(self) -> None:
        """Lance l'analyse du disque choisi ; pendant l'analyse, le même bouton l'arrête."""
        if self.en_cours():
            self.analyse.arret.set()
            self.bouton.setEnabled(False)
            self.bouton.setText("  Arrêt en cours…")
            return
        self.arreter()  # l'analyse précédente finit tout juste : on attend son thread avant de le remplacer
        self.occupe = True
        self.bouton.setText("  Arrêter l'analyse")
        self.choix.setEnabled(False)
        self.glissement.stop()
        self.progression.setValue(0)
        self.progression.show()
        self.info.setText("Analyse en cours : lecture des dossiers…")
        self.info.setObjectName("secondaire")
        repolir(self.info)
        self.statut.emit("Analyse du stockage en cours… (rien n'est modifié)")
        try:
            self.espace_utilise = psutil.disk_usage(self.racine).used
        except OSError:
            self.espace_utilise = 0  # progression inconnue : la barre reste au début, le texte avance
        self.analyse = AnalyseStockage(self.racine)
        self.analyse.avance.connect(self.avancer)
        self.analyse.termine.connect(self.fin)
        self.analyse.start()
        self.occupee.emit(True)

    def avancer(self, octets: float, nombre: int) -> None:
        """Progression estimée : la part de l'espace utilisé déjà comptée (Système, lui, n'est pas parcouru)."""
        self.glissement.stop()
        self.glissement.setEndValue(min(990, round(1000 * octets / self.espace_utilise)) if self.espace_utilise else 0)
        self.glissement.start()
        self.info.setText(f"Analyse en cours : {nombre_lisible(nombre)} fichiers parcourus, "
                          f"{taille_lisible(int(octets))} comptés…")

    def fin(self, resultat: dict | None) -> None:
        self.occupe = False
        self.progression.hide()
        self.bouton.setEnabled(True)
        self.choix.setEnabled(True)
        self.occupee.emit(False)
        if resultat is None:  # arrêtée : on garde ce qui était affiché
            self.statut.emit("Analyse du stockage arrêtée.")
            if self.resultat:
                self.afficher(self.resultat, animer=False)
            else:
                self._sans_resultat()
            return
        if "erreur" in resultat:
            self.statut.emit("L'analyse du stockage n'a pas pu aboutir.")
            self._sans_resultat(resultat["erreur"])
            return
        resultat["date"] = datetime.now()
        self.statut.emit(f"Stockage analysé en {resultat['duree']:.0f} s")
        self.afficher(resultat)

    def arreter(self) -> None:
        """Arrête l'analyse et attend la fin de son thread, avant que la page ou le thread soient détruits."""
        if self.analyse:
            self.analyse.arret.set()
            self.analyse.wait()

    def changer_disque(self, numero: int) -> None:
        self.racine = self.choix.itemData(numero)
        self._sans_resultat()

    # --- Actions (lecture seule) ---

    def montrer(self, chemin: str, dossier: bool) -> None:
        """Ouvre l'emplacement dans l'Explorateur : le dossier lui-même, ou celui du fichier, fichier sélectionné."""
        try:
            if dossier:
                os.startfile(chemin)  # comme un double-clic
            else:
                subprocess.Popen(["explorer", "/select,", chemin])
        except OSError:
            journal.exception("Impossible d'afficher %s", chemin)
            self.statut.emit("Cet emplacement n'a pas pu s'ouvrir.")
