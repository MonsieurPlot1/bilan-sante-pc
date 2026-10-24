"""Composants de l'interface : jauge du score, cartes des modules, conseils, graphique."""

from datetime import datetime
from typing import Callable

from PySide6.QtCore import (QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSequentialAnimationGroup, Qt,
                            QVariantAnimation)
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QScrollArea, QToolTip, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from ui import theme


def couleur_alpha(couleur: str, alpha: int) -> QColor:
    resultat = QColor(couleur)
    resultat.setAlpha(alpha)
    return resultat


def stylo_arrondi(couleur: QColor, epaisseur: float) -> QPen:
    stylo = QPen(couleur, epaisseur)
    stylo.setCapStyle(Qt.PenCapStyle.RoundCap)
    return stylo


def repolir(widget: QWidget) -> None:
    """Réapplique la feuille de style après un changement de propriété (ex. niveau d'une pastille)."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class Jauge(QWidget):
    """Score /100 en arc de cercle, qui se remplit avec une courte animation."""

    EPAISSEUR = 14
    OUVERTURE = 270  # degrés couverts par l'arc

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(210, 210)
        self.note: int | None = None
        self.valeur = 0.0
        self.couleur = theme.NIVEAUX["gris"]
        self.texte_vide = "–"  # avant toute analyse ; « ? » si l'analyse est incomplète
        self.animation = QVariantAnimation(self, duration=900, easingCurve=QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._avancer)
        self.setAccessibleName("Score : pas encore analysé")

    def definir(self, note: int | None, couleur: str, animer: bool = True) -> None:
        """`animer` faux : la jauge est remplie d'un coup (changement de couleurs, pas nouvelle note).

        L'animation part de la note affichée : à la relance, on voit le score monter ou descendre.
        """
        self.note, self.couleur = note, couleur
        self.texte_vide = "?"
        self.setAccessibleName(f"Score : {note} sur 100" if note is not None else "Score : analyse incomplète")
        self.animation.stop()
        if note is None or not animer:
            self._avancer(0.0 if note is None else float(note))
            return
        self.animation.setStartValue(self.valeur)
        self.animation.setEndValue(float(note))
        self.animation.start()

    def _avancer(self, valeur: float) -> None:
        self.valeur = valeur
        self.update()

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        marge = self.EPAISSEUR / 2 + 6
        zone = QRectF(self.rect()).adjusted(marge, marge, -marge, -marge)
        debut = (90 + self.OUVERTURE / 2) * 16  # angles Qt : en 1/16 de degré, depuis 3 h
        peintre.setPen(stylo_arrondi(QColor(theme.SURFACE_2), self.EPAISSEUR))
        peintre.drawArc(zone, int(debut), int(-self.OUVERTURE * 16))
        if self.valeur > 0:
            etendue = int(-self.OUVERTURE * 16 * self.valeur / 100)
            # Halo léger sous l'arc, puis l'arc lui-même.
            peintre.setPen(stylo_arrondi(couleur_alpha(self.couleur, 45), self.EPAISSEUR + 8))
            peintre.drawArc(zone, int(debut), etendue)
            peintre.setPen(stylo_arrondi(QColor(self.couleur), self.EPAISSEUR))
            peintre.drawArc(zone, int(debut), etendue)

        texte = self.texte_vide if self.note is None else str(round(self.valeur))
        peintre.setPen(QColor(theme.TEXTE))
        peintre.setFont(theme.police(40, QFont.Weight.DemiBold, titre=True))
        peintre.drawText(QRectF(0, 52, self.width(), 70), Qt.AlignmentFlag.AlignCenter, texte)
        peintre.setPen(QColor(theme.TEXTE_3))
        peintre.setFont(theme.police(10.5))
        peintre.drawText(QRectF(0, 122, self.width(), 24), Qt.AlignmentFlag.AlignCenter, "sur 100")


class BarreScore(QWidget):
    """Fine barre horizontale : part des points gardés par une partie."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(6)
        self.ratio, self.couleur = 0.0, theme.NIVEAUX["gris"]
        # Même durée et même courbe que la jauge : tout se remplit ensemble.
        self.animation = QVariantAnimation(self, duration=900, easingCurve=QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._avancer)

    def definir(self, ratio: float, couleur: str, animer: bool = True) -> None:
        self.couleur = couleur
        self.animation.stop()
        cible = max(0.0, min(1.0, ratio))
        if not animer:
            self._avancer(cible)
            return
        self.animation.setStartValue(self.ratio)  # depuis la valeur affichée : on voit le changement
        self.animation.setEndValue(cible)
        self.animation.start()

    def _avancer(self, ratio: float) -> None:
        self.ratio = ratio
        self.update()

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        peintre.setPen(Qt.PenStyle.NoPen)
        rayon = self.height() / 2
        peintre.setBrush(QColor(theme.SURFACE_2))
        peintre.drawRoundedRect(QRectF(self.rect()), rayon, rayon)
        if self.ratio > 0:
            peintre.setBrush(QColor(self.couleur))
            largeur = max(self.height(), self.width() * self.ratio)
            peintre.drawRoundedRect(QRectF(0, 0, largeur, self.height()), rayon, rayon)


class PastilleIcone(QWidget):
    """Icône dans un rond teinté, en tête des cartes."""

    def __init__(self, nom: str, couleur: str | None = None, taille: int = 36) -> None:
        super().__init__()
        self.setFixedSize(taille, taille)
        self.nom, self.couleur = nom, couleur or theme.ACCENT_CLAIR  # lue ici : elle change avec le mode

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        peintre.setPen(Qt.PenStyle.NoPen)
        peintre.setBrush(couleur_alpha(self.couleur, 34))
        peintre.drawEllipse(QRectF(self.rect()))
        cote = round(self.width() * 0.5)
        image = theme.pixmap_icone(self.nom, self.couleur, cote, self.devicePixelRatioF())
        peintre.drawPixmap((self.width() - cote) // 2, (self.height() - cote) // 2, image)


class Logo(QWidget):
    """Icône de l'application en tête de la fenêtre, nette à toutes les échelles d'affichage."""

    def __init__(self, taille: int = 48) -> None:  # 48 : une taille de l'ico, affichée telle quelle à l'échelle 100 %
        super().__init__()
        self.setFixedSize(taille, taille)

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.windowIcon().paint(peintre, self.rect())  # Qt choisit la taille de l'ico selon l'écran


def pastille(texte: str = "", niveau: str = "gris") -> QLabel:
    etiquette = QLabel(texte, objectName="pastille")
    etiquette.setProperty("niveau", niveau)
    return etiquette


def titre_section(texte: str) -> QLabel:
    etiquette = QLabel(texte.upper(), objectName="section")
    etiquette.setFont(theme.police(9, QFont.Weight.DemiBold))
    return etiquette


class Carte(QFrame):
    """Carte d'un module : icône, score partiel, barre, résumé et détail dépliable."""

    HAUTEUR_DETAIL_MIN, HAUTEUR_DETAIL_MAX = 110, 260

    def __init__(self, cle: str, titre: str, colonnes: list[str]) -> None:
        super().__init__(objectName="carte")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)  # bordure éclairée au survol (feuille de style)
        self.titre = QLabel(titre, font=theme.police(12.5, QFont.Weight.DemiBold, titre=True))
        self.points = pastille("–")
        self.barre = BarreScore()
        self.resume = QLabel("Pas encore analysé.", objectName="secondaire", wordWrap=True,
                             textFormat=Qt.TextFormat.PlainText)
        self.bouton = QPushButton("Voir le détail", objectName="lien", cursor=Qt.CursorShape.PointingHandCursor,
                                  icon=theme.icone("deplier", theme.ACCENT_CLAIR, 12))
        self.bouton.clicked.connect(self.basculer)
        self.bouton.hide()
        # Longs chemins coupés au milieu (« C:\Users\…\app.exe »), texte complet au survol.
        self.detail = QTreeWidget(rootIsDecorated=False, alternatingRowColors=True, uniformRowHeights=True,
                                  textElideMode=Qt.TextElideMode.ElideMiddle,
                                  horizontalScrollBarPolicy=Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail.setHeaderLabels(colonnes)
        entete_tableau = self.detail.header()
        for colonne in range(len(colonnes) - 1):
            entete_tableau.setSectionResizeMode(colonne, QHeaderView.ResizeMode.ResizeToContents)
        entete_tableau.setStretchLastSection(True)  # la dernière colonne prend la place qui reste
        entete_tableau.setMaximumSectionSize(140)  # les autres ne l'écrasent pas (texte complet au survol)
        entete_tableau.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        self.detail.hide()
        self.ouvert = False
        # Le détail se déplie et se replie en douceur (hauteur animée).
        self.animation_detail = QVariantAnimation(self, duration=220,
                                                  easingCurve=QEasingCurve.Type.OutCubic)
        self.animation_detail.valueChanged.connect(lambda hauteur: self.detail.setFixedHeight(round(hauteur)))
        self.animation_detail.finished.connect(lambda: self.detail.setVisible(self.ouvert))

        entete = QHBoxLayout()
        entete.setSpacing(12)
        entete.addWidget(PastilleIcone(cle))
        entete.addWidget(self.titre)
        entete.addStretch()
        entete.addWidget(self.points)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(18, 16, 18, 16)
        disposition.setSpacing(10)
        disposition.addLayout(entete)
        disposition.addWidget(self.barre)
        disposition.addWidget(self.resume)
        disposition.addWidget(self.bouton, alignment=Qt.AlignmentFlag.AlignLeft)
        disposition.addWidget(self.detail)

    def hauteur_detail(self) -> int:
        """Hauteur du tableau pour montrer ses lignes, sans place vide (bornée)."""
        lignes = self.detail.topLevelItemCount()
        contenu = (self.detail.header().sizeHint().height() + lignes * max(self.detail.sizeHintForRow(0), 0)
                   + 2 * self.detail.frameWidth() + 12)
        return max(self.HAUTEUR_DETAIL_MIN, min(self.HAUTEUR_DETAIL_MAX, contenu))

    def basculer(self) -> None:
        self.ouvert = not self.ouvert
        self.bouton.setText("Masquer le détail" if self.ouvert else "Voir le détail")
        self.bouton.setIcon(theme.icone("replier" if self.ouvert else "deplier", theme.ACCENT_CLAIR, 12))
        depart = 0 if self.detail.isHidden() else self.detail.maximumHeight()  # repart d'où il en est
        self.animation_detail.stop()
        if self.ouvert:
            self.detail.setFixedHeight(depart)
            self.detail.show()
        self.animation_detail.setStartValue(float(depart))
        self.animation_detail.setEndValue(float(self.hauteur_detail() if self.ouvert else 0))
        self.animation_detail.start()

    def remplir(self, points: str, ratio: float | None, constats: list[str], lignes: list[list[str]],
                erreur: str | None, animer: bool = True) -> None:
        niveau = "gris" if ratio is None else theme.niveau_ratio(ratio)
        self.points.setText(points)
        self.points.setProperty("niveau", "rouge" if erreur else niveau)
        repolir(self.points)
        self.barre.definir(ratio or 0.0, theme.NIVEAUX[niveau], animer)
        self.barre.setVisible(ratio is not None)  # une barre vide ferait croire à un 0 (hors score, erreur)
        self.resume.setText(erreur or "\n".join(constats))
        self.resume.setObjectName("erreur" if erreur else "secondaire")
        repolir(self.resume)
        self.detail.clear()
        elements = []
        for ligne in lignes:
            element = QTreeWidgetItem(ligne)
            for colonne, texte in enumerate(ligne):
                element.setToolTip(colonne, texte)  # texte complet, même coupé à l'affichage
            elements.append(element)
        self.detail.addTopLevelItems(elements)
        self.bouton.setVisible(bool(lignes))
        if self.ouvert and not lignes:
            self.basculer()
        elif self.ouvert and self.animation_detail.state() != QVariantAnimation.State.Running:
            self.detail.setFixedHeight(self.hauteur_detail())  # nouvelles lignes : nouvelle hauteur


class CarteConseil(QFrame):
    """Un conseil : numéro dans un rond, le texte, et un bouton « Ouvrir » s'il y a un endroit où agir."""

    def __init__(self, numero: int, texte: str, lien: tuple[str, str] | None = None,
                 ouvrir: Callable[[str], None] | None = None) -> None:
        super().__init__(objectName="conseil")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)  # bordure éclairée au survol (feuille de style)
        rond = QLabel(str(numero), alignment=Qt.AlignmentFlag.AlignCenter,
                      font=theme.police(10.5, QFont.Weight.Bold))
        rond.setFixedSize(28, 28)
        rond.setStyleSheet(f"color: {theme.ACCENT_CLAIR}; background: {theme.rgba(theme.ACCENT_CLAIR, 36)}; "
                           "border-radius: 14px;")
        corps = QLabel(texte, wordWrap=True, textFormat=Qt.TextFormat.PlainText,
                       textInteractionFlags=Qt.TextInteractionFlag.TextSelectableByMouse)
        droite = QVBoxLayout()
        droite.setSpacing(6)
        droite.addWidget(corps)
        self.bouton: QPushButton | None = None
        if lien and ouvrir:
            libelle, cible = lien
            self.bouton = QPushButton(libelle, objectName="lien", cursor=Qt.CursorShape.PointingHandCursor,
                                      icon=theme.icone("ouvrir", theme.ACCENT_CLAIR, 12))
            self.bouton.clicked.connect(lambda: ouvrir(cible))
            droite.addWidget(self.bouton, alignment=Qt.AlignmentFlag.AlignLeft)
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(16, 14, 18, 14)
        disposition.setSpacing(14)
        disposition.addWidget(rond, alignment=Qt.AlignmentFlag.AlignTop)
        disposition.addLayout(droite, 1)


def apparaitre(widget: QWidget, delai: int = 0) -> None:
    """Fait apparaître un nouvel élément en fondu, après `delai` ms (pour enchaîner plusieurs éléments)."""
    effet = QGraphicsOpacityEffect(widget, opacity=0.0)
    widget.setGraphicsEffect(effet)
    fondu = QPropertyAnimation(effet, b"opacity", duration=280, startValue=0.0, endValue=1.0,
                               easingCurve=QEasingCurve.Type.OutCubic)
    enchainement = QSequentialAnimationGroup(widget)  # supprimé avec l'élément s'il disparaît avant la fin
    enchainement.addPause(delai)
    enchainement.addAnimation(fondu)
    # Fini : l'effet est retiré, le texte redevient net et l'élément ne coûte plus rien à dessiner.
    enchainement.finished.connect(lambda: widget.setGraphicsEffect(None))
    enchainement.start()


class DefilementDoux(QScrollArea):
    """Zone de défilement où la molette de la souris fait glisser la page au lieu de la faire sauter.

    Même distance par cran que d'habitude ; les pavés tactiles, déjà fluides, ne changent pas.
    """

    def __init__(self, **proprietes) -> None:
        super().__init__(**proprietes)
        self.cible = 0
        self.glissement = QPropertyAnimation(self.verticalScrollBar(), b"value", self, duration=200,
                                             easingCurve=QEasingCurve.Type.OutCubic)

    def wheelEvent(self, evenement) -> None:
        crans = evenement.angleDelta().y() / 120
        if not evenement.pixelDelta().isNull() or not crans:
            super().wheelEvent(evenement)
            return
        barre = self.verticalScrollBar()
        # Plusieurs crans rapides s'ajoutent : on repart de la destination, pas de la position du moment.
        depart = self.cible if self.glissement.state() == QPropertyAnimation.State.Running else barre.value()
        pas = barre.singleStep() * QApplication.wheelScrollLines()
        self.cible = round(max(barre.minimum(), min(barre.maximum(), depart - crans * pas)))
        self.glissement.stop()
        self.glissement.setEndValue(self.cible)
        self.glissement.start()
        evenement.accept()


class Fondu(QWidget):
    """Passage en douceur d'un affichage à l'autre : l'ancienne image s'efface sur la nouvelle.

    Seules deux images figées sont mélangées à chaque étape : rien d'autre n'est redessiné
    pendant le fondu, qui reste fluide même sur un PC lent.
    """

    def __init__(self, parent: QWidget, ancienne: QPixmap, duree: int) -> None:
        super().__init__(parent, objectName="fondu")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)  # couvre tout : rien n'est redessiné dessous
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # les clics passent au travers
        self.ancienne, self.nouvelle, self.progres = ancienne, None, 0.0
        self.animation = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=duree,
                                           easingCurve=QEasingCurve.Type.InOutSine)
        self.animation.valueChanged.connect(self._avancer)
        self.animation.finished.connect(self.deleteLater)
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()

    def demarrer(self, nouvelle: QPixmap) -> None:
        self.nouvelle = nouvelle
        self.animation.start()

    def _avancer(self, progres: float) -> None:
        self.progres = progres
        self.update()

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        if self.nouvelle is not None:
            peintre.drawPixmap(0, 0, self.nouvelle)
        peintre.setOpacity(1 - self.progres)
        peintre.drawPixmap(0, 0, self.ancienne)


class Graphique(QWidget):
    """Mini-graphique de l'évolution du score (une seule série : pas de légende)."""

    MARGE_GAUCHE, MARGE_DROITE, MARGE_HAUT, MARGE_BAS = 30, 18, 14, 10

    def __init__(self) -> None:
        super().__init__(minimumHeight=120, mouseTracking=True)
        self.entrees: list[dict] = []
        self.progres = 1.0  # part de la courbe déjà dessinée, de gauche à droite
        self.trace = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=700,
                                       easingCurve=QEasingCurve.Type.InOutCubic)
        self.trace.valueChanged.connect(self._avancer)

    def afficher(self, entrees: list[dict], animer: bool = True) -> None:
        """`animer` : la courbe se dessine de gauche à droite (seulement si elle change)."""
        animer = animer and entrees != self.entrees
        self.entrees = entrees
        scores = ", ".join(str(e["score"]) for e in entrees)
        self.setAccessibleDescription(f"Évolution du score sur les dernières analyses : {scores}")
        self.trace.stop()
        self._avancer(0.0 if animer else 1.0)  # dès la première image : pas de courbe entière qui clignote
        if animer:
            self.trace.start()

    def _avancer(self, progres: float) -> None:
        self.progres = progres
        self.update()

    def _y(self, score: float) -> float:
        hauteur = self.height() - self.MARGE_HAUT - self.MARGE_BAS
        return self.MARGE_HAUT + hauteur * (1 - score / 100)

    def _positions(self) -> list[QPointF]:
        largeur = self.width() - self.MARGE_GAUCHE - self.MARGE_DROITE
        pas = largeur / max(1, len(self.entrees) - 1)
        return [QPointF(self.MARGE_GAUCHE + i * pas, self._y(e["score"])) for i, e in enumerate(self.entrees)]

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        if len(self.entrees) < 2:
            peintre.setPen(QColor(theme.TEXTE_3))
            peintre.setFont(theme.police(9.5))
            peintre.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Le graphique apparaîtra après deux analyses.")
            return
        # Repères discrets à 0, 50 et 100.
        peintre.setFont(theme.police(8))
        for valeur in (0, 50, 100):
            y = self._y(valeur)
            peintre.setPen(QPen(QColor(theme.BORDURE), 1, Qt.PenStyle.DashLine if valeur == 50 else Qt.PenStyle.SolidLine))
            peintre.drawLine(QPointF(self.MARGE_GAUCHE, y), QPointF(self.width() - self.MARGE_DROITE, y))
            peintre.setPen(QColor(theme.TEXTE_3))
            peintre.drawText(QRectF(0, y - 8, self.MARGE_GAUCHE - 8, 16),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(valeur))
        points = self._positions()
        # Courbe dévoilée de gauche à droite pendant l'animation (les repères, eux, sont déjà là).
        peintre.setClipRect(QRectF(0, 0, points[0].x() + (points[-1].x() - points[0].x() + 8) * self.progres,
                                   self.height()))
        # Aire légèrement teintée sous la courbe.
        aire = QPainterPath(QPointF(points[0].x(), self._y(0)))
        for point in points:
            aire.lineTo(point)
        aire.lineTo(QPointF(points[-1].x(), self._y(0)))
        degrade = QLinearGradient(0, self.MARGE_HAUT, 0, self._y(0))
        degrade.setColorAt(0, couleur_alpha(theme.ACCENT_CLAIR, 60))
        degrade.setColorAt(1, couleur_alpha(theme.ACCENT_CLAIR, 0))
        peintre.fillPath(aire, degrade)
        peintre.setPen(QPen(QColor(theme.ACCENT_CLAIR), 2))
        peintre.drawPolyline(points)
        peintre.setPen(QPen(QColor(theme.SURFACE), 2))  # anneau couleur du fond autour des points
        peintre.setBrush(QColor(theme.ACCENT_CLAIR))
        for point in points:
            peintre.drawEllipse(point, 4, 4)
        # Seule la dernière valeur est écrite, dans la couleur du texte (elle apparaît en fin de tracé).
        peintre.setClipping(False)
        peintre.setOpacity(max(0.0, (self.progres - 0.8) / 0.2))
        peintre.setPen(QColor(theme.TEXTE))
        peintre.setFont(theme.police(9, QFont.Weight.DemiBold))
        dernier = points[-1]
        peintre.drawText(QRectF(dernier.x() - 30, dernier.y() - 24, 40, 16), Qt.AlignmentFlag.AlignCenter,
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
