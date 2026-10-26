"""Composants de l'interface : anneau du score, cartes, conseils, graphique, sélecteur à segments,
barre du disque, confirmations, annonces et infobulles. Les matières (verre, lueur, ombres) sont dans ui/verre.py."""

from datetime import datetime
from typing import Callable, NamedTuple

from math import ceil

from PySide6.QtCore import (QEasingCurve, QEvent, QModelIndex, QPoint, QPointF, QPropertyAnimation, QRect, QRectF,
                            QSequentialAnimationGroup, QSize, Qt, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor, QFont, QFontMetricsF, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap, QRegion, QTextLayout, QTextOption)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QDialog, QFrame, QGraphicsOpacityEffect,
                               QHBoxLayout, QHeaderView, QLabel, QPushButton, QScrollArea, QSizePolicy, QStyle,
                               QStyleOptionViewItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

import config
from ui import theme
from ui.verre import Verre, arrondi, dessiner_ombre, flouter, peindre_verre

# Teinte de la tuile d'icône de chaque partie du bilan (jamais une couleur d'état).
TUILES = {"demarrage": "violet", "disque": "bleu", "fichiers": "aqua", "ressources": "magenta",
          "redemarrage": "gris", "alimentation": "bleu", "jeux": "magenta", "batterie": "aqua", "historique": "bleu"}


def couleur_alpha(couleur: str, alpha: int) -> QColor:
    resultat = QColor(couleur)
    resultat.setAlpha(alpha)
    return resultat


def melange(a: QColor, b: QColor, part_de_a: float) -> QColor:
    """Couleur entre `b` (0) et `a` (1), comme deux images superposées en transparence."""
    return QColor(*(round(x * part_de_a + y * (1 - part_de_a))
                    for x, y in ((a.red(), b.red()), (a.green(), b.green()), (a.blue(), b.blue()))))


def stylo_arrondi(couleur: QColor | QBrush, epaisseur: float) -> QPen:
    stylo = QPen(couleur, epaisseur)
    stylo.setCapStyle(Qt.PenCapStyle.RoundCap)
    return stylo


def repolir(widget: QWidget) -> None:
    """Réapplique la feuille de style après un changement de propriété (ex. niveau d'une pastille)."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def bouton(texte: str = "", style: str = "", icone: str | None = None, couleur: str | None = None,
           taille_icone: int = 14, **proprietes) -> QPushButton:
    """Bouton du thème : main au survol ; le cadre de focus n'apparaît qu'au clavier, pas après un clic.

    `style` : « principal », « teinte », « lien »… (voir la feuille de style) ; sans style, un bouton secondaire.
    """
    resultat = QPushButton(texte, objectName=style or "secondaire", cursor=Qt.CursorShape.PointingHandCursor,
                           **proprietes)
    resultat.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    if icone:
        resultat.setIcon(theme.icone(icone, couleur or theme.TEXTE, taille_icone))
        resultat.setIconSize(QSize(taille_icone, taille_icone))
    return resultat


class Jauge(QWidget):
    """Score /100 en anneau, comme les anneaux d'activité d'Apple et l'icône de l'application.

    Il se remplit avec une courte animation, dans un dégradé qui s'éclaire vers son départ.
    """

    EPAISSEUR = 15

    def __init__(self, taille: int = 176) -> None:
        super().__init__()
        self.setFixedSize(taille, taille)
        self.note: int | None = None
        self.valeur = 0.0
        self.couleur = theme.VIFS["gris"]
        self.texte_vide = "–"  # avant toute analyse ; « ? » si l'analyse est incomplète
        self.animation = QVariantAnimation(self, duration=900, easingCurve=QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._avancer)
        self.setAccessibleName("Score : pas encore analysé")

    def definir(self, note: int | None, couleur: str, animer: bool = True) -> None:
        """`animer` faux : l'anneau est rempli d'un coup (changement de couleurs, pas nouvelle note).

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
        couleur = QColor(self.couleur)
        piste = QColor(theme.REMPLI) if self.note is None else couleur_alpha(self.couleur, 44 if theme.CLAIR else 52)
        peintre.setPen(stylo_arrondi(piste, self.EPAISSEUR))
        peintre.drawEllipse(zone)
        if self.valeur > 0:
            part = self.valeur / 100
            # Angles en degrés, dans le sens inverse des aiguilles, depuis 3 h : le départ est juste avant midi,
            # pour que le bout arrondi du début de l'anneau soit dans la teinte claire.
            degrade = QConicalGradient(zone.center(), 95)
            degrade.setColorAt(0, couleur)
            degrade.setColorAt(max(0.0, 0.986 - part), couleur)
            degrade.setColorAt(1, melange(QColor(theme.BLANC), couleur, 0.28))
            peintre.setPen(stylo_arrondi(couleur_alpha(self.couleur, 40), self.EPAISSEUR + 8))  # halo léger
            peintre.drawArc(zone, 90 * 16, round(-360 * 16 * part))
            peintre.setPen(stylo_arrondi(QBrush(degrade), self.EPAISSEUR))
            peintre.drawArc(zone, 90 * 16, round(-360 * 16 * part))

        texte = self.texte_vide if self.note is None else str(round(self.valeur))
        milieu = self.height() / 2
        peintre.setPen(QColor(theme.TEXTE))
        peintre.setFont(theme.police("score"))
        peintre.drawText(QRectF(0, milieu - 40, self.width(), 60), Qt.AlignmentFlag.AlignCenter, texte)
        peintre.setPen(QColor(theme.TEXTE_3))
        peintre.setFont(theme.police("legende"))
        peintre.drawText(QRectF(0, milieu + 18, self.width(), 20), Qt.AlignmentFlag.AlignCenter, "sur 100")


class BarreScore(QWidget):
    """Fine barre en capsule : part des points gardés par une partie (ou part d'une catégorie)."""

    def __init__(self, hauteur: int = 6) -> None:
        super().__init__()
        self.setFixedHeight(hauteur)
        self.ratio, self.couleur = 0.0, theme.VIFS["gris"]
        # Même durée et même courbe que l'anneau : tout se remplit ensemble.
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
        rayon = self.height() / 2
        peintre.fillPath(arrondi(QRectF(self.rect()), rayon), QColor(theme.REMPLI))
        if self.ratio > 0:
            largeur = max(self.height(), self.width() * self.ratio)
            peintre.fillPath(arrondi(QRectF(0, 0, largeur, self.height()), rayon), QColor(self.couleur))


class BarreEmpilee(QWidget):
    """Barre d'un disque découpée en parts de couleur (comme le stockage d'un Mac) ; le reste est l'espace libre.

    Les parts se dévoilent de gauche à droite. Pas d'infobulle : les chiffres sont écrits à côté et dans la légende.
    """

    ECART = 2  # px entre deux parts : elles se distinguent sans trait autour

    def __init__(self, hauteur: int = 12) -> None:
        super().__init__()
        self.setFixedHeight(hauteur)
        self.parts: list[tuple[float, str]] = []  # (part du disque, couleur)
        self.progres = 1.0
        self.animation = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=900,
                                           easingCurve=QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._avancer)

    def definir(self, parts: list[tuple[float, str]], animer: bool = True) -> None:
        self.parts = parts
        self.animation.stop()
        self._avancer(0.0 if animer else 1.0)
        if animer:
            self.animation.start()

    def _avancer(self, progres: float) -> None:
        self.progres = progres
        self.update()

    def _rects(self) -> list[QRectF]:
        rects, x = [], 0.0
        for part, _couleur in self.parts:
            largeur = part * self.width()
            rects.append(QRectF(x, 0, max(0.0, largeur - self.ECART), self.height()))
            x += largeur
        return rects

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        capsule = arrondi(QRectF(self.rect()), self.height() / 2)
        peintre.fillPath(capsule, QColor(theme.REMPLI))
        peintre.setClipPath(capsule)
        peintre.setClipRect(QRectF(0, 0, self.width() * self.progres, self.height()),
                            Qt.ClipOperation.IntersectClip)
        for rect, (_part, couleur) in zip(self._rects(), self.parts):
            if rect.width() >= 1:
                peintre.fillRect(rect, QColor(couleur))


class Legende(QWidget):
    """Légende d'une barre : pastille de couleur, nom et taille de chaque part, sur plusieurs lignes si besoin."""

    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, str, str]] = []  # (couleur, nom, taille)
        self._disposees: dict[float, tuple[list[QPointF], float]] = {}  # par largeur : calculé une fois
        politique = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        politique.setHeightForWidth(True)
        self.setSizePolicy(politique)

    def definir(self, elements: list[tuple[str, str, str]]) -> None:
        self.elements = elements
        self._disposees.clear()
        self.setAccessibleDescription(", ".join(f"{nom} : {taille}" for _c, nom, taille in elements))
        self.updateGeometry()
        self.update()

    def _polices(self) -> tuple[QFont, QFont]:
        return theme.police("legende"), theme.police("legende_forte")

    def _positions(self, largeur: float) -> tuple[list[QPointF], float]:
        """Place de chaque élément, sur plusieurs lignes si besoin. La mise en page la demande plusieurs fois
        par image (pendant un dépliage, un redimensionnement) : gardée par largeur."""
        if largeur not in self._disposees:
            self._disposees[largeur] = self._disposer(largeur)
        return self._disposees[largeur]

    def _disposer(self, largeur: float) -> tuple[list[QPointF], float]:
        nom, valeur = (QFontMetricsF(f) for f in self._polices())
        hauteur_ligne = nom.height() + 6
        positions, x, y = [], 0.0, 0.0
        for _couleur, texte, taille in self.elements:
            besoin = 14 + nom.horizontalAdvance(texte) + 6 + valeur.horizontalAdvance(taille)
            if x > 0 and x + besoin > largeur:
                x, y = 0.0, y + hauteur_ligne
            positions.append(QPointF(x, y))
            x += besoin + 20
        return positions, (y + hauteur_ligne if self.elements else 0.0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, largeur: int) -> int:
        return round(self._positions(largeur)[1])

    def sizeHint(self) -> QSize:
        return QSize(400, self.heightForWidth(max(self.width(), 400)))

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        police_nom, police_valeur = self._polices()
        nom, valeur = QFontMetricsF(police_nom), QFontMetricsF(police_valeur)
        positions, _hauteur = self._positions(self.width())
        for position, (couleur, texte, taille) in zip(positions, self.elements):
            milieu = position.y() + nom.height() / 2
            pastille_ = QColor(couleur)
            if pastille_.alpha() < 128:  # couleur presque transparente (l'espace libre) : un cercle cerné
                peintre.setPen(QPen(QColor(theme.TEXTE_3), 1))
                peintre.setBrush(Qt.BrushStyle.NoBrush)
                peintre.drawEllipse(QPointF(position.x() + 4, milieu), 3.5, 3.5)
            else:
                peintre.setPen(Qt.PenStyle.NoPen)
                peintre.setBrush(pastille_)
                peintre.drawEllipse(QPointF(position.x() + 4, milieu), 4, 4)
            peintre.setFont(police_nom)
            peintre.setPen(QColor(theme.TEXTE_2))
            x = position.x() + 14
            peintre.drawText(QPointF(x, position.y() + nom.ascent()), texte)
            peintre.setFont(police_valeur)
            peintre.setPen(QColor(theme.TEXTE))
            peintre.drawText(QPointF(x + nom.horizontalAdvance(texte) + 6, position.y() + valeur.ascent()), taille)


class TuileIcone(QWidget):
    """Icône blanche sur une tuile de couleur aux coins arrondis, comme dans les Réglages d'Apple."""

    def __init__(self, nom: str, teinte: str = "bleu", taille: int = 32) -> None:
        super().__init__()
        self.setFixedSize(taille, taille)
        self.nom, self.teinte = nom, teinte

    def paintEvent(self, _evenement) -> None:
        couleur = QColor(theme.TEINTES.get(self.teinte) or theme.VIFS[self.teinte])  # lue ici : elle suit le mode
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        forme = arrondi(rect, self.width() * 0.28)
        degrade = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        degrade.setColorAt(0, couleur.lighter(118))
        degrade.setColorAt(1, couleur)
        peintre.fillPath(forme, degrade)
        peintre.setPen(QPen(couleur_alpha(theme.BLANC, 60), 1))  # reflet discret sur le bord haut
        peintre.drawPath(arrondi(rect.adjusted(0.5, 0.5, -0.5, -0.5), self.width() * 0.28))
        cote = round(self.width() * 0.52)
        image = theme.pixmap_icone(self.nom, theme.BLANC, cote, self.devicePixelRatioF())
        peintre.drawPixmap(QPointF((self.width() - cote) / 2, (self.height() - cote) / 2), image)


class Logo(QWidget):
    """Icône de l'application en tête de la fenêtre, nette à toutes les échelles d'affichage."""

    def __init__(self, taille: int = 32) -> None:  # 32 : une taille de l'ico, affichée telle quelle à l'échelle 100 %
        super().__init__()
        self.setFixedSize(taille, taille)

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.windowIcon().paint(peintre, self.rect())  # Qt choisit la taille de l'ico selon l'écran


def pastille(texte: str = "", niveau: str = "gris") -> QLabel:
    etiquette = QLabel(texte, objectName="pastille", font=theme.police("legende_forte"))
    etiquette.setProperty("niveau", niveau)
    # Hauteur de son texte, jamais celle de la ligne qui la contient : elle reste une petite capsule.
    etiquette.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return etiquette


def etiquette_couleur(texte: str, couleur: str) -> QLabel:
    """Un point de couleur devant un texte discret : relie une ligne à sa part dans une barre ou une légende."""
    return QLabel(f"<span style='color:{couleur}'>●</span>&nbsp;&nbsp;{texte}", objectName="secondaire",
                  font=theme.police("legende"), textFormat=Qt.TextFormat.RichText)


def titre_section(texte: str) -> QLabel:
    return QLabel(texte, objectName="section", font=theme.police("section"))


def pied_de_page() -> QWidget:
    """Bas de chaque page : la promesse de l'application et sa version."""
    bouclier = QLabel()
    bouclier.setPixmap(theme.pixmap_icone("bouclier", theme.NIVEAUX["vert"], 14))
    pied = QWidget()
    ligne = QHBoxLayout(pied)
    ligne.setContentsMargins(4, 10, 4, 0)
    ligne.setSpacing(8)
    ligne.addWidget(bouclier)
    ligne.addWidget(QLabel("Tes données restent sur ton PC. L'application ne modifie rien sans ton accord.",
                           objectName="discret", font=theme.police("legende")))
    ligne.addStretch()
    ligne.addWidget(QLabel(f"Version {config.VERSION}", objectName="discret", font=theme.police("legende")))
    return pied


class Carte(Verre):
    """Carte d'une partie du bilan : tuile d'icône, points, barre, résumé et détail dépliable."""

    HAUTEUR_DETAIL_MIN, HAUTEUR_DETAIL_MAX = 110, 260

    def __init__(self, cle: str, titre: str, colonnes: list[str]) -> None:
        super().__init__(rayon=20)
        self.titre = QLabel(titre, font=theme.police("carte"))
        self.points = pastille("–")
        self.barre = BarreScore()
        self.barre.hide()  # avant l'analyse : une barre vide ferait croire à un 0
        self.resume = QLabel("Pas encore analysé.", objectName="secondaire", wordWrap=True,
                             textFormat=Qt.TextFormat.PlainText)
        self.bouton = bouton("Voir le détail", "lien", "deplier", theme.ACCENT_CLAIR, 11)
        self.bouton.clicked.connect(self.basculer)
        self.bouton.hide()
        # Longs chemins coupés au milieu (« C:\Users\…\app.exe »), texte complet au survol s'il est coupé.
        self.detail = QTreeWidget(rootIsDecorated=False, uniformRowHeights=True,
                                  textElideMode=Qt.TextElideMode.ElideMiddle,
                                  horizontalScrollBarPolicy=Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
                                  focusPolicy=Qt.FocusPolicy.TabFocus)
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
        self.animation_detail = QVariantAnimation(self, duration=240, easingCurve=QEasingCurve.Type.OutCubic)
        self.animation_detail.valueChanged.connect(lambda hauteur: self.detail.setFixedHeight(round(hauteur)))
        self.animation_detail.finished.connect(lambda: self.detail.setVisible(self.ouvert))

        entete = QHBoxLayout()
        entete.setSpacing(12)
        entete.addWidget(TuileIcone(cle, TUILES[cle], 30))
        entete.addWidget(self.titre)
        entete.addStretch()
        entete.addWidget(self.points)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(20, 18, 20, 16)
        disposition.setSpacing(10)
        disposition.addLayout(entete)
        disposition.addSpacing(2)
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
        self.bouton.setIcon(theme.icone("replier" if self.ouvert else "deplier", theme.ACCENT_CLAIR, 11))
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
        self.barre.definir(ratio or 0.0, theme.VIFS[niveau], animer)
        self.barre.setVisible(ratio is not None)  # une barre vide ferait croire à un 0 (hors score, erreur)
        self.resume.setText(erreur or "\n".join(constats))
        self.resume.setObjectName("erreur" if erreur else "secondaire")
        repolir(self.resume)
        self.detail.clear()
        elements = []
        for ligne in lignes:
            element = QTreeWidgetItem(ligne)
            for colonne, texte in enumerate(ligne):
                element.setToolTip(colonne, texte)  # montré au survol seulement s'il est coupé (texte_infobulle)
            elements.append(element)
        self.detail.addTopLevelItems(elements)
        self.bouton.setVisible(bool(lignes))
        if self.ouvert and not lignes:
            self.basculer()
        elif self.ouvert and self.animation_detail.state() != QVariantAnimation.State.Running:
            self.detail.setFixedHeight(self.hauteur_detail())  # nouvelles lignes : nouvelle hauteur


class CarteConseil(Verre):
    """Un conseil : son rang dans un rond, le texte, et dessous un bouton « Ouvrir » s'il y a un endroit où agir
    (sous le texte, il ne le serre jamais en colonne étroite, même quand la fenêtre est petite)."""

    def __init__(self, numero: int, texte: str, lien: tuple[str, str] | None = None,
                 ouvrir: Callable[[str], None] | None = None) -> None:
        super().__init__(rayon=18)
        rond = QLabel(str(numero), alignment=Qt.AlignmentFlag.AlignCenter,
                      font=theme.police("fort"))
        rond.setFixedSize(28, 28)
        rond.setStyleSheet(f"color: {theme.ACCENT_CLAIR}; background: {theme.rgba(theme.ACCENT_CLAIR, 40)}; "
                           "border-radius: 14px;")
        corps = QLabel(texte, wordWrap=True, textFormat=Qt.TextFormat.PlainText, font=theme.police("corps"),
                       textInteractionFlags=Qt.TextInteractionFlag.TextSelectableByMouse)
        droite = QVBoxLayout()
        droite.setSpacing(10)
        droite.addWidget(corps)
        self.bouton: QPushButton | None = None
        if lien and ouvrir:
            libelle, cible = lien
            self.bouton = bouton(f" {libelle}", "teinte", "ouvrir", theme.ACCENT_CLAIR, 12)
            self.bouton.clicked.connect(lambda: ouvrir(cible))
            droite.addWidget(self.bouton, alignment=Qt.AlignmentFlag.AlignLeft)
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(18, 16, 20, 16)
        disposition.setSpacing(14)
        disposition.addWidget(rond, alignment=Qt.AlignmentFlag.AlignTop)
        disposition.addLayout(droite, 1)


def apparaitre(widget: QWidget, delai: int = 0) -> None:
    """Fait apparaître un nouvel élément en fondu, après `delai` ms (pour enchaîner plusieurs éléments)."""
    effet = QGraphicsOpacityEffect(widget, opacity=0.0)
    widget.setGraphicsEffect(effet)
    fondu = QPropertyAnimation(effet, b"opacity", duration=280, startValue=0.0, endValue=1.0,
                               easingCurve=QEasingCurve.Type.OutCubic)
    if isinstance(widget, Verre) and widget.ombre:
        fondu.valueChanged.connect(lambda _valeur: widget.rafraichir_ombre())  # son ombre apparaît avec elle
    enchainement = QSequentialAnimationGroup(widget)  # supprimé avec l'élément s'il disparaît avant la fin
    enchainement.addPause(delai)
    enchainement.addAnimation(fondu)
    # Fini : l'effet est retiré, le texte redevient net et l'élément ne coûte plus rien à dessiner.
    enchainement.finished.connect(lambda: widget.setGraphicsEffect(None))
    enchainement.start()


class DefilementDoux(QScrollArea):
    """Zone de défilement transparente (la lueur du fond reste en place) où la molette fait glisser la page
    au lieu de la faire sauter. Même distance par cran que d'habitude ; les pavés tactiles ne changent pas."""

    def __init__(self, **proprietes) -> None:
        super().__init__(**proprietes)
        self.viewport().setAutoFillBackground(False)
        self.cible = 0
        self.glissement = QPropertyAnimation(self.verticalScrollBar(), b"value", self, duration=220,
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


def courbe_douce(points: list[QPointF]) -> QPainterPath:
    """Courbe lisse qui passe par chaque point sans jamais dépasser ses voisins (interpolation monotone) :
    pas de faux pic ni de creux inventé entre deux analyses."""
    chemin = QPainterPath(points[0])
    pentes = [(b.y() - a.y()) / max(1e-6, b.x() - a.x()) for a, b in zip(points, points[1:])]
    tangentes = [pentes[0]]
    for avant, apres in zip(pentes, pentes[1:]):
        tangentes.append(0.0 if avant * apres <= 0 else 2 / (1 / avant + 1 / apres))
    tangentes.append(pentes[-1])
    for i, (a, b) in enumerate(zip(points, points[1:])):
        tiers = (b.x() - a.x()) / 3
        chemin.cubicTo(QPointF(a.x() + tiers, a.y() + tangentes[i] * tiers),
                       QPointF(b.x() - tiers, b.y() - tangentes[i + 1] * tiers), b)
    return chemin


class Graphique(QWidget):
    """Mini-graphique de l'évolution du score (une seule série : pas de légende)."""

    MARGE_GAUCHE, MARGE_DROITE, MARGE_HAUT, MARGE_BAS = 30, 18, 16, 10

    def __init__(self) -> None:
        super().__init__(minimumHeight=130, mouseTracking=True)
        self.entrees: list[dict] = []
        self.survol: int | None = None  # point sous la souris
        self.progres = 1.0  # part de la courbe déjà dessinée, de gauche à droite
        self.trace = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=700,
                                       easingCurve=QEasingCurve.Type.InOutCubic)
        self.trace.valueChanged.connect(self._avancer)

    def afficher(self, entrees: list[dict], animer: bool = True) -> None:
        """`animer` : la courbe se dessine de gauche à droite (seulement si elle change)."""
        animer = animer and entrees != self.entrees
        self.entrees, self.survol = entrees, None
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
            peintre.setFont(theme.police("legende"))
            peintre.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Le graphique apparaîtra après deux analyses.")
            return
        # Repères discrets à 0, 50 et 100.
        peintre.setFont(theme.police("legende"))
        for valeur in (0, 50, 100):
            y = round(self._y(valeur)) + 0.5
            trait = Qt.PenStyle.DashLine if valeur == 50 else Qt.PenStyle.SolidLine
            peintre.setPen(QPen(QColor(theme.SEPARATEUR), 1, trait))
            peintre.drawLine(QPointF(self.MARGE_GAUCHE, y), QPointF(self.width() - self.MARGE_DROITE, y))
            peintre.setPen(QColor(theme.TEXTE_3))
            peintre.drawText(QRectF(0, y - 8, self.MARGE_GAUCHE - 8, 16),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(valeur))
        points = self._positions()
        courbe = courbe_douce(points)
        # Courbe dévoilée de gauche à droite pendant l'animation (les repères, eux, sont déjà là).
        peintre.setClipRect(QRectF(0, 0, points[0].x() + (points[-1].x() - points[0].x() + 8) * self.progres,
                                   self.height()))
        aire = QPainterPath(courbe)  # aire légèrement teintée sous la courbe
        aire.lineTo(QPointF(points[-1].x(), self._y(0)))
        aire.lineTo(QPointF(points[0].x(), self._y(0)))
        aire.closeSubpath()
        degrade = QLinearGradient(0, self.MARGE_HAUT, 0, self._y(0))
        degrade.setColorAt(0, couleur_alpha(theme.ACCENT_CLAIR, 70 if theme.CLAIR else 50))
        degrade.setColorAt(1, couleur_alpha(theme.ACCENT_CLAIR, 0))
        peintre.fillPath(aire, degrade)
        peintre.setPen(stylo_arrondi(QColor(theme.ACCENT_CLAIR), 2))
        peintre.drawPath(courbe)
        # Points : un anneau couleur de la carte autour de chacun ; le dernier et celui survolé, plus grands.
        peintre.setPen(QPen(QColor(theme.SURFACE), 2))
        peintre.setBrush(QColor(theme.ACCENT_CLAIR))
        for numero, point in enumerate(points):
            rayon = 5 if numero in (len(points) - 1, self.survol) else 3.5
            peintre.drawEllipse(point, rayon, rayon)
        peintre.setClipping(False)
        if self.survol is not None:
            x = round(points[self.survol].x()) + 0.5
            peintre.setPen(QPen(QColor(theme.SEPARATEUR), 1))
            peintre.drawLine(QPointF(x, self.MARGE_HAUT - 6), QPointF(x, self._y(0)))
        # Seule la dernière valeur est écrite, dans la couleur du texte (elle apparaît en fin de tracé).
        peintre.setOpacity(max(0.0, (self.progres - 0.8) / 0.2))
        peintre.setPen(QColor(theme.TEXTE))
        peintre.setFont(theme.police("legende_forte"))
        dernier = points[-1]
        peintre.drawText(QRectF(dernier.x() - 30, dernier.y() - 26, 40, 16), Qt.AlignmentFlag.AlignCenter,
                         str(self.entrees[-1]["score"]))

    def mouseMoveEvent(self, evenement) -> None:
        points = self._positions()
        if len(points) < 2:
            return
        # Zone de survol plus large que le point : le plus proche horizontalement.
        index = min(range(len(points)), key=lambda i: abs(points[i].x() - evenement.position().x()))
        if index != self.survol:
            self.survol = index
            self.update()
        date = datetime.fromisoformat(self.entrees[index]["date"])
        Infobulle.instance().montrer(f"{date:%d/%m/%Y à %H:%M} : {self.entrees[index]['score']} sur 100",
                                     evenement.globalPosition().toPoint(), self)

    def leaveEvent(self, evenement) -> None:
        self.survol = None
        self.update()
        super().leaveEvent(evenement)


class BarreHaut(QWidget):
    """Barre du haut (application, onglets, mode). Dès que la page défile, elle devient du verre dépoli : le
    contenu qui vient de passer dessous s'y devine, flouté, avec un trait fin en bas, comme sur Mac et iPhone.

    La barre ne recouvre pas la page : elle peint elle-même, floutée, la bande de page juste au-dessus de la
    partie visible. Même effet qu'un verre posé sur la page, mais Qt peut toujours faire défiler la page en
    décalant l'image déjà dessinée (rien ne la recouvre) : le défilement reste fluide.
    """

    MARGE_FLOU = 16  # contenu pris en plus autour de la bande : le flou reste régulier jusqu'aux bords
    ECHELLE = 0.5  # la bande est dessinée en petit avant d'être floutée : deux fois moins de pixels

    def __init__(self) -> None:
        super().__init__(objectName="barre")
        self.setFixedHeight(theme.HAUTEUR_BARRE)
        self.zone = None  # zone de défilement suivie (celle de l'onglet affiché)
        self.verre = 0.0  # 0 en haut de la page, 1 dès qu'elle a défilé de quelques pixels
        self.flou: QImage | None = None
        # Page défilée : ce qui est sous la barre peut changer (animations) ; on le relit de temps en temps.
        self.relecture = QTimer(self, interval=300)
        self.relecture.timeout.connect(self._relire)

    def suivre(self, zone) -> None:
        if self.zone is not None:
            self.zone.verticalScrollBar().valueChanged.disconnect(self._relire)
        self.zone = zone
        zone.verticalScrollBar().valueChanged.connect(self._relire)
        self._relire()

    def _relire(self) -> None:
        position = self.zone.verticalScrollBar().value() if self.zone is not None else 0
        self.verre = min(1.0, position / 16)  # apparaît en douceur sur les premiers pixels
        if position <= 0 or not self.isVisible():
            self.flou = None
            self.relecture.stop()
        else:
            self.flou = self._contenu_floute(position)
            if not self.relecture.isActive():
                self.relecture.start()
        self.update()

    def _contenu_floute(self, position: int) -> QImage:
        """La bande de page qui vient de passer sous la barre, dessinée en petit puis floutée."""
        page, marge, echelle = self.zone.widget(), self.MARGE_FLOU, self.ECHELLE
        source = QRect(0, position - self.height() - marge, self.width(), self.height() + 2 * marge)
        image = QImage(max(1, round(source.width() * echelle)), max(1, round(source.height() * echelle)),
                       QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor(theme.FOND))  # au-dessus du haut de la page : la couleur du haut de la fenêtre
        visible = source.intersected(page.rect())
        if not visible.isEmpty():
            peintre = QPainter(image)
            peintre.scale(echelle, echelle)
            page.render(peintre, visible.topLeft() - source.topLeft(), QRegion(visible))
            peintre.end()
        floue = flouter(image, 6)
        return floue.copy(0, round(marge * echelle), floue.width(), round(self.height() * echelle))

    def paintEvent(self, _evenement) -> None:
        if self.verre <= 0:
            return  # page en haut : la barre se confond avec le fond
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = QRectF(self.rect())
        peintre.setOpacity(self.verre)
        if self.flou is not None:
            peintre.drawImage(rect, self.flou)
        peintre.fillRect(rect, QColor(theme.VERRE_BARRE))
        # Le haut se fond dans la barre de titre de Windows, unie : pas de raccord visible entre les deux.
        haut = QLinearGradient(0, 0, 0, 14)
        uni, transparent = QColor(theme.FOND), QColor(theme.FOND)
        transparent.setAlpha(0)
        haut.setColorAt(0, uni)
        haut.setColorAt(1, transparent)
        peintre.fillRect(QRectF(0, 0, rect.width(), 14), haut)
        peintre.fillRect(QRectF(0, rect.height() - 1, rect.width(), 1), QColor(theme.SEPARATEUR))


class Segmente(QFrame):
    """Sélecteur à segments, comme sur Mac et iPhone : une pastille glisse sous le choix actif."""

    choisi = Signal(int)  # clic sur un segment (souris ou clavier)

    def __init__(self, libelles: list[str], actuel: int = 0) -> None:
        super().__init__(objectName="segmente")
        self.groupe = QButtonGroup(self)  # un seul choix à la fois
        ligne = QHBoxLayout(self)
        ligne.setContentsMargins(3, 3, 3, 3)
        ligne.setSpacing(2)
        for numero, libelle in enumerate(libelles):
            segment = bouton(libelle, "segment", checkable=True)
            self.groupe.addButton(segment, numero)
            ligne.addWidget(segment)
        self.groupe.button(actuel).setChecked(True)
        self.curseur = QRectF()
        self.glissement = QVariantAnimation(self, duration=260, easingCurve=QEasingCurve.Type.OutCubic)
        self.glissement.valueChanged.connect(self._placer)
        self.groupe.idToggled.connect(lambda numero, coche: coche and self._glisser())
        self.groupe.idClicked.connect(self.choisi)

    def _cible(self) -> QRectF:
        return QRectF(self.groupe.checkedButton().geometry())

    def _glisser(self) -> None:
        if self.curseur.isNull() or not self.isVisible():
            self.update()  # pas encore affiché : la pastille sera placée directement
            return
        self.glissement.stop()
        self.glissement.setStartValue(self.curseur)
        self.glissement.setEndValue(self._cible())
        self.glissement.start()

    def _placer(self, rect: QRectF) -> None:
        self.curseur = rect
        self.update()

    def paintEvent(self, _evenement) -> None:
        if self.glissement.state() != QVariantAnimation.State.Running:
            self.curseur = self._cible()  # suit aussi les changements de taille
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        peintre.fillPath(arrondi(rect, rect.height() / 2), QColor(theme.REMPLI))
        if theme.CLAIR:
            dessiner_ombre(peintre, self.curseur, round(self.curseur.height() / 2), flou=3, decalage=1,
                           couleur=theme.voile(theme.ENCRE, 0.18))
        peintre.fillPath(arrondi(self.curseur, self.curseur.height() / 2), QColor(theme.CURSEUR))


class Feuille(QDialog):
    """Confirmation en verre, au milieu de la fenêtre floutée et assombrie (comme les alertes d'Apple).

    Remplace les boîtes de dialogue de Windows : même allure, claire ou sombre, que le reste de l'application.
    `exec()` vaut QDialog.DialogCode.Accepted si l'action est confirmée.
    """

    LARGEUR = 440

    def __init__(self, parent: QWidget, titre: str, texte: str, details: str = "", confirmer: str = "OK",
                 annuler: str | None = "Annuler", destructif: bool = False, icone: str = "info") -> None:
        fenetre = parent.window()
        super().__init__(fenetre, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(titre)
        self._texte, self._details = texte, details
        # Derrière : la fenêtre figée et floutée, calculée une fois.
        self.fond = flouter(fenetre.grab().toImage(), 14) if fenetre.isVisible() else None
        self.setGeometry(fenetre.geometry())  # couvre la fenêtre, sous la barre de titre de Windows

        self.panneau = Verre(rayon=22, ombre=False, objectName="feuille",
                             teintes=(theme.VERRE_FEUILLE, theme.VERRE_FEUILLE))
        self.panneau.setParent(self)
        entete = QHBoxLayout()
        entete.setSpacing(12)
        entete.addWidget(TuileIcone(icone, "rouge" if destructif else "bleu", 34), alignment=Qt.AlignmentFlag.AlignTop)
        entete.addWidget(QLabel(titre, font=theme.police("carte"), wordWrap=True), 1)
        corps = QLabel(texte, wordWrap=True, font=theme.police("corps"), textFormat=Qt.TextFormat.PlainText)
        precision = QLabel(details, objectName="secondaire", wordWrap=True, textFormat=Qt.TextFormat.PlainText)
        if not details:  # jamais setVisible(True) ici : sans parent, il s'ouvrirait en petite fenêtre
            precision.hide()

        self.bouton_confirmer = bouton(confirmer, "destructif" if destructif else "principal")
        self.bouton_confirmer.clicked.connect(self.accept)
        boutons = QHBoxLayout()
        boutons.setSpacing(10)
        boutons.addStretch()
        self.bouton_annuler: QPushButton | None = None
        if annuler:
            self.bouton_annuler = bouton(annuler)
            self.bouton_annuler.clicked.connect(self.reject)
            boutons.addWidget(self.bouton_annuler)
        boutons.addWidget(self.bouton_confirmer)
        # Une action définitive ne se confirme jamais d'un simple appui sur Entrée.
        self._defaut = self.bouton_annuler if destructif and self.bouton_annuler else self.bouton_confirmer
        self._defaut.setDefault(True)

        disposition = QVBoxLayout(self.panneau)
        disposition.setContentsMargins(24, 22, 24, 20)
        disposition.setSpacing(12)
        disposition.addLayout(entete)
        disposition.addWidget(corps)
        disposition.addWidget(precision)
        disposition.addSpacing(6)
        disposition.addLayout(boutons)
        self.panneau.setFixedWidth(min(self.LARGEUR, max(300, self.width() - 48)))
        self.panneau.setFixedHeight(self.panneau.heightForWidth(self.panneau.width())
                                    if self.panneau.hasHeightForWidth() else self.panneau.sizeHint().height())

        self.apparition = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=200,
                                            easingCurve=QEasingCurve.Type.OutCubic)
        self.apparition.valueChanged.connect(self._avancer)

    def texte(self) -> str:
        return self._texte

    def details(self) -> str:
        return self._details

    def bouton_defaut(self) -> QPushButton:
        return self._defaut

    def showEvent(self, evenement) -> None:
        super().showEvent(evenement)
        self._avancer(0.0)
        self._defaut.setFocus()
        self.apparition.start()

    def _avancer(self, progres: float) -> None:
        """Le panneau apparaît en fondu en remontant un peu, comme posé sur la fenêtre."""
        self.setWindowOpacity(progres)
        self.panneau.move((self.width() - self.panneau.width()) // 2,
                          round((self.height() - self.panneau.height()) * 0.42 + (1 - progres) * 14))
        self.update()

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.fond is not None:
            peintre.drawImage(QRectF(self.rect()), self.fond)
        else:
            peintre.fillRect(self.rect(), QColor(theme.FOND))
        peintre.fillRect(self.rect(), QColor(theme.VOILE_FEUILLE))
        dessiner_ombre(peintre, QRectF(self.panneau.geometry()), self.panneau.rayon, flou=26, decalage=14,
                       couleur=theme.voile(theme.NOIR, 0.16 if theme.CLAIR else 0.40))


class Annonce(QWidget):
    """Petit message en verre en bas de la fenêtre, qui s'efface seul (remplace la barre d'état)."""

    MARGE = 18  # place de l'ombre autour de la pastille

    def __init__(self, ambiance: QWidget) -> None:
        super().__init__(ambiance, objectName="annonce")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # ne gêne aucun clic
        self.ambiance = ambiance
        self.dernier = ""
        self.symbole = QLabel()
        self.message = QLabel(wordWrap=True, textFormat=Qt.TextFormat.PlainText,
                              font=theme.police("corps"))
        ligne = QHBoxLayout(self)
        ligne.setContentsMargins(self.MARGE + 16, self.MARGE + 10, self.MARGE + 20, self.MARGE + 10)
        ligne.setSpacing(10)
        ligne.addWidget(self.symbole, alignment=Qt.AlignmentFlag.AlignTop)
        ligne.addWidget(self.message, 1)
        self.effet = QGraphicsOpacityEffect(self, opacity=0.0)
        self.setGraphicsEffect(self.effet)
        self.progres = 0.0
        self.mouvement = QVariantAnimation(self, duration=220, easingCurve=QEasingCurve.Type.OutCubic)
        self.mouvement.valueChanged.connect(self._avancer)
        self.mouvement.finished.connect(lambda: self.progres == 0 and self.hide())
        self.minuterie = QTimer(self, singleShot=True)
        self.minuterie.timeout.connect(lambda: self._animer(0.0))
        ambiance.superpositions.append(self)
        self.hide()

    def texte(self) -> str:
        """Le dernier message annoncé (même une fois effacé)."""
        return self.dernier

    def montrer(self, texte: str, nature: str = "info", duree: int = 4500) -> None:
        """`nature` : « info », « valide » (action réussie) ou « erreur »."""
        self.dernier = texte
        couleur, icone = {"info": (theme.TEXTE_2, "info"), "valide": (theme.NIVEAUX["vert"], "valide"),
                          "erreur": (theme.NIVEAUX["rouge"], "avertissement")}[nature]
        self.symbole.setPixmap(theme.pixmap_icone(icone, couleur, 16, self.devicePixelRatioF()))
        # Une ligne si le message tient, sinon plusieurs lignes sur la largeur maximale.
        largeur_max = min(520, max(200, self.ambiance.width() - 160))
        largeur = self.message.fontMetrics().horizontalAdvance(texte) + 2
        self.message.setWordWrap(largeur > largeur_max)
        self.message.setFixedWidth(min(largeur, largeur_max))
        self.message.setText(texte)
        self.adjustSize()
        self.placer()
        self.show()
        self.raise_()
        self._animer(1.0)
        self.minuterie.start(duree)

    def _animer(self, cible: float) -> None:
        self.mouvement.stop()
        self.mouvement.setStartValue(self.progres)
        self.mouvement.setEndValue(cible)
        self.mouvement.start()

    def _avancer(self, progres: float) -> None:
        self.progres = progres
        self.effet.setOpacity(progres)
        self.placer()

    def placer(self) -> None:
        self.move((self.ambiance.width() - self.width()) // 2,
                  self.ambiance.height() - self.height() - 6 + round((1 - self.progres) * 12))

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        rect = QRectF(self.rect()).adjusted(self.MARGE, self.MARGE, -self.MARGE, -self.MARGE)
        rayon = min(rect.height() / 2, 20)
        dessiner_ombre(peintre, rect, round(rayon), flou=12, decalage=6,
                       couleur=theme.voile(theme.NOIR, 0.14 if theme.CLAIR else 0.40))
        peindre_verre(peintre, rect, rayon, theme.VERRE_FEUILLE, theme.VERRE_FEUILLE)


def _option_cellule(vue: QAbstractItemView, index: QModelIndex) -> QStyleOptionViewItem:
    """Ce que le tableau donne au style pour dessiner le texte de la cellule (police, place, alignement)."""
    option = QStyleOptionViewItem()
    option.initFrom(vue)
    option.widget, option.font, option.rect = vue, vue.font(), vue.visualRect(index)
    option.text = index.data(Qt.ItemDataRole.DisplayRole) or ""
    option.features = QStyleOptionViewItem.ViewItemFeature.HasDisplay
    option.displayAlignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    return option


def cellule_coupee(vue: QAbstractItemView, index: QModelIndex) -> bool:
    """Vrai si le texte de la cellule est coupé (« C:\\Users\\…\\app.exe ») : il demande plus de place que la
    largeur de sa colonne, marges du thème comprises (le calcul même qui règle la largeur des colonnes)."""
    option = _option_cellule(vue, index)
    return vue.itemDelegateForIndex(index).sizeHint(option, index).width() > option.rect.width()


class Demande(NamedTuple):
    """Une infobulle à montrer : son texte et la zone de l'écran où elle reste valable. Si elle montre en entier
    un texte coupé : `ancre`, où le poser par-dessus lui (bord gauche du texte, milieu de sa hauteur) pour ne rien
    cacher d'autre, et sa police, pour que le texte semble simplement s'allonger."""
    texte: str
    zone: QRect
    ancre: QPoint | None = None
    police: QFont | None = None


def texte_infobulle(widget: QWidget, position: QPoint) -> Demande:
    """L'infobulle sous `position` (coordonnées de `widget`).

    Dans un tableau : celle de la cellule, mais si elle ne fait que répéter son texte, seulement quand il est coupé.
    Ailleurs : celle du widget ou, à défaut, du plus proche parent qui en a une (comme Qt).
    """
    vue = widget.parentWidget()
    if isinstance(vue, QAbstractItemView) and widget is vue.viewport():
        index = vue.indexAt(position)
        texte = index.data(Qt.ItemDataRole.ToolTipRole) or ""
        rect = vue.visualRect(index)
        zone = QRect(widget.mapToGlobal(rect.topLeft()), rect.size())
        if not texte or texte != index.data(Qt.ItemDataRole.DisplayRole):
            return Demande(texte, zone)
        if not cellule_coupee(vue, index):
            return Demande("", zone)
        style = vue.style()
        debut = (style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, _option_cellule(vue, index), vue).left()
                 + style.pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, None, vue) + 1)
        return Demande(texte, zone, widget.mapToGlobal(QPoint(debut, rect.center().y())), vue.font())
    while widget is not None:
        if widget.toolTip():
            zone = QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())
            if isinstance(widget, QLabel) and widget.toolTip() == widget.text():  # son propre texte, coupé
                return Demande(widget.toolTip(), zone, widget.mapToGlobal(QPoint(0, widget.height() // 2)),
                               widget.font())
            return Demande(widget.toolTip(), zone)
        widget = None if widget.isWindow() else widget.parentWidget()
    return Demande("", QRect())


class Infobulle(QWidget):
    """Infobulle au survol, dans la matière de l'application : une petite plaque du verre bleu nuit des annonces,
    bordée comme les cartes, aux coins arrondis, avec une ombre douce (couleurs, police, arrondi : ui/theme.py).

    Elle remplace celle de Qt partout : posée sur l'application, elle reçoit avant eux les demandes d'infobulle de
    tous les widgets (`setToolTip`, cellules d'un tableau). La bulle de Qt est une fenêtre opaque : sous Windows, un
    arrondi de la feuille de style y laisse des coins carrés. Celle-ci est une fenêtre transparente où seules la
    plaque et son ombre sont dessinées.
    """

    FLOU, DECALAGE = 6, 3  # ombre de la plaque
    MARGE = 2 * FLOU + DECALAGE  # place de l'ombre autour de la plaque
    LARGEUR_MAX = 420  # au-delà, le texte passe à la ligne
    DUREE = 10000  # ms : elle s'efface seule, comme celle de Windows
    # Évènements qui l'effacent, où qu'ils arrivent : on clique, on tape, on fait défiler ou on quitte la fenêtre.
    EFFACENT = {QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick, QEvent.Type.Wheel,
                QEvent.Type.KeyPress, QEvent.Type.WindowDeactivate}
    SURVEILLES = EFFACENT | {QEvent.Type.ToolTip, QEvent.Type.Leave}
    _instance: "Infobulle | None" = None

    @classmethod
    def instance(cls) -> "Infobulle":
        """L'infobulle de l'application, créée et posée sur l'application au premier appel."""
        if cls._instance is None:
            cls._instance = cls()
            QApplication.instance().installEventFilter(cls._instance)
        return cls._instance

    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # rien autour de la plaque arrondie
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.texte = ""
        self.lignes = QTextLayout()
        self.marges = theme.MARGES_INFOBULLE  # marge intérieure de la plaque
        self.plaque = QRectF()
        self.proprietaire: QWidget | None = None  # widget survolé
        self.zone = QRect()  # zone de l'écran où elle reste valable (le widget, la cellule)
        # La souris peut quitter la zone sans que son widget le signale (d'une cellule à l'autre) : vérifié souvent.
        self.veille = QTimer(self, interval=100)
        self.veille.timeout.connect(self._verifier)
        self.fin = QTimer(self, singleShot=True, interval=self.DUREE)
        self.fin.timeout.connect(self.cacher)
        self.apparition = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=120,
                                            easingCurve=QEasingCurve.Type.OutCubic)
        self.apparition.valueChanged.connect(self.setWindowOpacity)

    def eventFilter(self, objet, evenement) -> bool:
        genre = evenement.type()
        if genre not in self.SURVEILLES:  # presque tous les évènements de l'application : rendus aussitôt
            return False
        if genre == QEvent.Type.ToolTip:
            if not isinstance(objet, QWidget):
                return False
            demande = texte_infobulle(objet, evenement.pos())
            if demande.texte:
                self.montrer(demande.texte, evenement.globalPos(), objet, demande.zone, demande.ancre, demande.police)
            else:
                self.cacher()
            return True  # traitée ici : la bulle grise de Qt n'apparaît jamais
        if (genre != QEvent.Type.Leave or objet is self.proprietaire) and self.isVisible():
            self.cacher()
        return False

    def montrer(self, texte: str, curseur: QPoint, proprietaire: QWidget, zone: QRect | None = None,
                ancre: QPoint | None = None, police: QFont | None = None) -> None:
        """`texte` sous le pointeur (ou par-dessus le texte coupé qu'il complète, à `ancre`, dans sa `police`), tant
        que le pointeur reste dans `zone` (coordonnées de l'écran ; tout `proprietaire` par défaut). Rappelée pendant
        le survol (graphique), elle suit le pointeur sans réapparaître."""
        self.proprietaire = proprietaire
        self.zone = zone if zone is not None else QRect(proprietaire.mapToGlobal(QPoint(0, 0)), proprietaire.size())
        police = police or theme.police(theme.POLICE_INFOBULLE)
        marges = theme.MARGES_INFOBULLE if ancre is None else theme.MARGES_TEXTE_COMPLET
        if (texte, police, marges) != (self.texte, self.lignes.font(), self.marges):
            self.texte, self.marges = texte, marges
            self._disposer(police)
            self.update()
        self._placer(curseur, ancre)
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
            self.apparition.start()
        self.veille.start()
        self.fin.start()

    def cacher(self) -> None:
        self.veille.stop()
        self.fin.stop()
        self.apparition.stop()
        self.proprietaire = None
        self.hide()

    def _disposer(self, police: QFont) -> None:
        """Le texte sur une ligne s'il tient, sinon sur plusieurs : coupé entre deux mots ou, pour un long chemin,
        n'importe où. La fenêtre prend la taille de la plaque et de son ombre."""
        self.lignes = QTextLayout(self.texte, police)
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.lignes.setTextOption(option)
        self.lignes.beginLayout()
        largeur = hauteur = 0.0
        while (ligne := self.lignes.createLine()).isValid():
            ligne.setLineWidth(self.LARGEUR_MAX)
            ligne.setPosition(QPointF(0, hauteur))
            largeur, hauteur = max(largeur, ligne.naturalTextWidth()), hauteur + ligne.height()
        self.lignes.endLayout()
        cote, haut = self.marges
        self.plaque = QRectF(self.MARGE, self.MARGE, ceil(largeur) + 2 * cote, ceil(hauteur) + 2 * haut)
        self.resize(round(self.plaque.width()) + 2 * self.MARGE, round(self.plaque.height()) + 2 * self.MARGE)

    def _placer(self, curseur: QPoint, ancre: QPoint | None) -> None:
        """Par-dessus le texte coupé qu'elle complète (ses lettres sur les siennes), sinon centrée sous le pointeur
        ou au-dessus s'il n'y a pas la place ; dans la fenêtre si elle y tient, toujours entière dans l'écran."""
        largeur, hauteur = self.plaque.width(), self.plaque.height()
        limites = (QApplication.screenAt(curseur) or QApplication.primaryScreen()).availableGeometry()
        fenetre = limites.intersected(self.proprietaire.window().geometry())
        if fenetre.width() >= largeur + 8 and fenetre.height() >= hauteur + 8:
            limites = fenetre
        limites = limites.adjusted(4, 4, -4, -4)
        if ancre is not None:
            x, y = ancre.x() - self.marges[0], ancre.y() - hauteur / 2
        else:
            x, y = curseur.x() - largeur / 2, curseur.y() + 22  # sous la flèche de la souris
            if y + hauteur > limites.bottom():
                y = curseur.y() - 10 - hauteur
        x = min(max(x, limites.left()), limites.right() - largeur)
        self.move(round(x) - self.MARGE, round(y) - self.MARGE)

    def _verifier(self) -> None:
        try:
            present = self.proprietaire is not None and self.proprietaire.isVisible()
        except RuntimeError:  # widget supprimé entre-temps (liste refaite)
            present = False
        if not present or not self.zone.contains(QCursor.pos()):
            self.cacher()

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        rayon = min(theme.RAYON_INFOBULLE, int(self.plaque.height() // 2))  # plaque fine : bouts tout ronds
        dessiner_ombre(peintre, self.plaque, rayon, flou=self.FLOU, decalage=self.DECALAGE,
                       couleur=theme.voile(theme.NOIR, 0.14 if theme.CLAIR else 0.40))
        peindre_verre(peintre, self.plaque, rayon, theme.VERRE_FEUILLE, theme.VERRE_FEUILLE)
        peintre.setPen(QColor(theme.TEXTE))
        self.lignes.draw(peintre, self.plaque.topLeft() + QPointF(*self.marges))
