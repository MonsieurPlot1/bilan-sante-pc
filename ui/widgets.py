"""Composants de l'interface : jauge du score, cartes des modules, conseils, graphique."""

from datetime import datetime

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QToolTip, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

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

    def definir(self, note: int | None, couleur: str) -> None:
        self.note, self.couleur = note, couleur
        self.texte_vide = "?"
        self.setAccessibleName(f"Score : {note} sur 100" if note is not None else "Score : analyse incomplète")
        self.animation.stop()
        if note is None:
            self.valeur = 0.0
            self.update()
            return
        self.animation.setStartValue(0.0)
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

    def definir(self, ratio: float, couleur: str) -> None:
        self.ratio, self.couleur = max(0.0, min(1.0, ratio)), couleur
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

    def __init__(self, nom: str, couleur: str = theme.ACCENT_CLAIR, taille: int = 36) -> None:
        super().__init__()
        self.setFixedSize(taille, taille)
        self.nom, self.couleur = nom, couleur

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        peintre.setPen(Qt.PenStyle.NoPen)
        peintre.setBrush(couleur_alpha(self.couleur, 34))
        peintre.drawEllipse(QRectF(self.rect()))
        cote = round(self.width() * 0.5)
        image = theme.pixmap_icone(self.nom, self.couleur, cote, self.devicePixelRatioF())
        peintre.drawPixmap((self.width() - cote) // 2, (self.height() - cote) // 2, image)


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

    def __init__(self, cle: str, titre: str, colonnes: list[str]) -> None:
        super().__init__(objectName="carte")
        self.titre = QLabel(titre, font=theme.police(12.5, QFont.Weight.DemiBold, titre=True))
        self.points = pastille("–")
        self.barre = BarreScore()
        self.resume = QLabel("Pas encore analysé.", objectName="secondaire", wordWrap=True,
                             textFormat=Qt.TextFormat.PlainText)
        self.bouton = QPushButton("Voir le détail", objectName="lien", cursor=Qt.CursorShape.PointingHandCursor,
                                  icon=theme.icone("deplier", theme.ACCENT_CLAIR, 12))
        self.bouton.clicked.connect(self.basculer)
        self.bouton.hide()
        self.detail = QTreeWidget(rootIsDecorated=False, alternatingRowColors=True, minimumHeight=150,
                                  maximumHeight=260, uniformRowHeights=True)
        self.detail.setHeaderLabels(colonnes)
        self.detail.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.detail.header().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        self.detail.hide()

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

    def basculer(self) -> None:
        visible = not self.detail.isVisible()
        self.detail.setVisible(visible)
        self.bouton.setText("Masquer le détail" if visible else "Voir le détail")
        self.bouton.setIcon(theme.icone("replier" if visible else "deplier", theme.ACCENT_CLAIR, 12))

    def remplir(self, points: str, ratio: float | None, constats: list[str], lignes: list[list[str]],
                erreur: str | None) -> None:
        niveau = "gris" if ratio is None else theme.niveau_ratio(ratio)
        self.points.setText(points)
        self.points.setProperty("niveau", "rouge" if erreur else niveau)
        repolir(self.points)
        self.barre.definir(ratio or 0.0, theme.NIVEAUX[niveau])
        self.resume.setText(erreur or "\n".join(constats))
        self.resume.setObjectName("erreur" if erreur else "secondaire")
        repolir(self.resume)
        self.detail.clear()
        self.detail.addTopLevelItems([QTreeWidgetItem(ligne) for ligne in lignes])
        self.bouton.setVisible(bool(lignes))
        if not lignes and self.detail.isVisible():
            self.basculer()


class CarteConseil(QFrame):
    """Un conseil : numéro dans un rond, puis le texte."""

    def __init__(self, numero: int, texte: str) -> None:
        super().__init__(objectName="conseil")
        rond = QLabel(str(numero), alignment=Qt.AlignmentFlag.AlignCenter,
                      font=theme.police(10.5, QFont.Weight.Bold))
        rond.setFixedSize(28, 28)
        rond.setStyleSheet(f"color: {theme.ACCENT_CLAIR}; background: rgba(122, 162, 255, 36); border-radius: 14px;")
        corps = QLabel(texte, wordWrap=True, textFormat=Qt.TextFormat.PlainText,
                       textInteractionFlags=Qt.TextInteractionFlag.TextSelectableByMouse)
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(16, 14, 18, 14)
        disposition.setSpacing(14)
        disposition.addWidget(rond, alignment=Qt.AlignmentFlag.AlignTop)
        disposition.addWidget(corps, 1)


class Graphique(QWidget):
    """Mini-graphique de l'évolution du score (une seule série : pas de légende)."""

    MARGE_GAUCHE, MARGE_DROITE, MARGE_HAUT, MARGE_BAS = 30, 18, 14, 10

    def __init__(self) -> None:
        super().__init__(minimumHeight=120, mouseTracking=True)
        self.entrees: list[dict] = []

    def afficher(self, entrees: list[dict]) -> None:
        self.entrees = entrees
        scores = ", ".join(str(e["score"]) for e in entrees)
        self.setAccessibleDescription(f"Évolution du score sur les dernières analyses : {scores}")
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
        # Seule la dernière valeur est écrite, dans la couleur du texte.
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
