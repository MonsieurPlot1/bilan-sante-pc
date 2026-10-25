"""Matières de l'interface : la lueur du fond, le verre dépoli, le flou et les ombres.

Tout est dessiné par l'application, pas par Windows : même rendu sur tous les PC, même quand les effets de
transparence de Windows sont coupés. Ce qui coûte (lueur, ombres, flou) est calculé une fois et gardé en image :
rien de lourd n'est refait pendant le défilement.
"""

import os
from functools import cache, lru_cache

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QRect, QRectF, QSequentialAnimationGroup, Qt,
                            QVariantAnimation)
from PySide6.QtGui import (QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                           QRadialGradient)
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QLayout, QVBoxLayout, QWidget

from ui import theme

LISSE = Qt.TransformationMode.SmoothTransformation
LIBRE = Qt.AspectRatioMode.IgnoreAspectRatio


def flouter(image: QImage, force: int) -> QImage:
    """Flou rapide : l'image réduite `force` fois puis agrandie, en deux étapes pour un flou doux.

    Bien moins coûteux qu'un vrai flou gaussien, et la différence ne se voit pas sous le voile du verre.
    """
    largeur, hauteur = image.width(), image.height()
    moitie = max(2, force // 2)
    etape = image.scaled(max(1, largeur // moitie), max(1, hauteur // moitie), LIBRE, LISSE)
    petite = etape.scaled(max(1, largeur // force), max(1, hauteur // force), LIBRE, LISSE)
    resultat = petite.scaled(etape.size(), LIBRE, LISSE).scaled(largeur, hauteur, LIBRE, LISSE)
    resultat.setDevicePixelRatio(image.devicePixelRatio())
    return resultat


def arrondi(rect: QRectF, rayon: float) -> QPainterPath:
    chemin = QPainterPath()
    chemin.addRoundedRect(rect, rayon, rayon)
    return chemin


# --- Ombres ---

FLOU_OMBRE, DECALAGE_OMBRE = 18, 6  # px : douceur et descente de l'ombre des cartes


@cache
def _ombre(rayon: int, flou: int, decalage: int, couleur: str, ratio: float) -> QPixmap:
    """Ombre d'une petite carte de référence, découpée ensuite en 9 morceaux (coins, bords).

    La forme de la carte est retirée de l'image : l'ombre ne fonce pas le verre, qui est transparent.
    """
    cote, marge = 2 * rayon + 2, 2 * flou
    taille = cote + 2 * marge
    image = QImage(round(taille * ratio), round(taille * ratio), QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(ratio)
    image.fill(Qt.GlobalColor.transparent)
    peintre = QPainter(image)
    peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
    peintre.fillPath(arrondi(QRectF(marge, marge + decalage, cote, cote), rayon), QColor(couleur))
    peintre.end()
    image = flouter(image, max(2, round(flou * ratio)))
    peintre = QPainter(image)
    peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
    peintre.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    peintre.fillPath(arrondi(QRectF(marge, marge, cote, cote), rayon), Qt.GlobalColor.black)
    peintre.end()
    return QPixmap.fromImage(image)


def dessiner_ombre(peintre: QPainter, rect: QRectF, rayon: int, flou: int = FLOU_OMBRE,
                   decalage: int = DECALAGE_OMBRE, couleur: str | None = None) -> None:
    """Ombre douce autour de `rect` (une carte de coins `rayon`), étirée à partir de l'ombre de référence."""
    ratio = peintre.device().devicePixelRatioF()
    image = _ombre(rayon, flou, decalage, couleur or theme.OMBRE, ratio)
    marge = 2 * flou
    coin = marge + rayon  # le coin arrondi entier ; il reste au milieu une bande de 2 px, étirée le long des bords
    taille = 2 * rayon + 2 + 2 * marge
    cible = rect.adjusted(-marge, -marge, marge, marge)
    xs = [cible.left(), cible.left() + coin, cible.right() - coin, cible.right()]
    ys = [cible.top(), cible.top() + coin, cible.bottom() - coin, cible.bottom()]
    sources = [0, coin, taille - coin, taille]
    for i in range(3):
        for j in range(3):
            if i == j == 1 or xs[i + 1] <= xs[i] or ys[j + 1] <= ys[j]:
                continue  # le centre reste vide : c'est la place de la carte
            peintre.drawPixmap(QRectF(xs[i], ys[j], xs[i + 1] - xs[i], ys[j + 1] - ys[j]), image,
                               QRectF(sources[i] * ratio, sources[j] * ratio, (sources[i + 1] - sources[i]) * ratio,
                                      (sources[j + 1] - sources[j]) * ratio))


# --- Verre ---

def peindre_verre(peintre: QPainter, rect: QRectF, rayon: float, haut: str | None = None,
                  bas: str | None = None) -> None:
    """Une plaque de verre dépoli : voile dégradé, trait extérieur discret et filet de lumière sur le bord."""
    peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
    exterieur = arrondi(rect.adjusted(0.5, 0.5, -0.5, -0.5), rayon)
    voile = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    voile.setColorAt(0, QColor(haut or theme.VERRE_HAUT))
    voile.setColorAt(1, QColor(bas or theme.VERRE_BAS))
    peintre.fillPath(exterieur, voile)
    peintre.setBrush(Qt.BrushStyle.NoBrush)
    peintre.setPen(QPen(QColor(theme.CONTOUR), 1))
    peintre.drawPath(exterieur)
    reflet = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    reflet.setColorAt(0, QColor(theme.REFLET_HAUT))
    reflet.setColorAt(min(1.0, 48 / max(1.0, rect.height())), QColor(theme.REFLET_BAS))  # la lumière vient d'en haut
    reflet.setColorAt(1, QColor(theme.REFLET_BAS))
    peintre.setPen(QPen(reflet, 1))
    peintre.drawPath(arrondi(rect.adjusted(1.5, 1.5, -1.5, -1.5), max(0.0, rayon - 1)))


class Verre(QFrame):
    """Carte en verre dépoli. `ombre` : ombre portée sous la carte (dessinée par la Page qui la contient).

    `separateurs` : une liste de la carte dont les éléments sont séparés par un trait fin, comme chez Apple.
    """

    def __init__(self, rayon: int = 20, ombre: bool = True, objectName: str = "carte",
                 teintes: tuple[str, str] | None = None) -> None:
        super().__init__(objectName=objectName)
        self.rayon, self.ombre, self.teintes = rayon, ombre, teintes
        self.separateurs: QLayout | None = None

    def paintEvent(self, _evenement) -> None:
        peintre = QPainter(self)
        haut, bas = self.teintes or (None, None)
        peindre_verre(peintre, QRectF(self.rect()), self.rayon, haut, bas)
        if self.separateurs is not None:
            self._separer(peintre)

    def _separer(self, peintre: QPainter) -> None:
        elements = [self.separateurs.itemAt(i).widget() for i in range(self.separateurs.count())]
        visibles = [element for element in elements if element is not None and not element.isHidden()]
        peintre.setPen(QPen(QColor(theme.SEPARATEUR), 1))
        for dessus, dessous in zip(visibles, visibles[1:]):
            y = round((dessus.geometry().bottom() + dessous.geometry().top()) / 2) + 0.5
            peintre.drawLine(QPointF(dessus.geometry().left() + 12, y), QPointF(dessus.geometry().right() - 12, y))

    # L'ombre est hors de la carte : la Page la redessine quand la carte bouge, change de taille ou apparaît.
    def moveEvent(self, evenement) -> None:
        super().moveEvent(evenement)
        self._ombre_a_jour(QRect(evenement.oldPos(), self.size()))

    def resizeEvent(self, evenement) -> None:
        super().resizeEvent(evenement)
        self._ombre_a_jour(QRect(self.pos(), evenement.oldSize()))

    def rafraichir_ombre(self) -> None:
        self._ombre_a_jour(self.geometry())

    def _ombre_a_jour(self, ancienne: QRect) -> None:
        page = self.parentWidget()
        while page is not None and not isinstance(page, Page):
            page = page.parentWidget()
        if not self.ombre or page is None or self.parentWidget() is None:
            return
        marge = 2 * FLOU_OMBRE + DECALAGE_OMBRE
        decalage = self.parentWidget().mapTo(page, QPoint(0, 0))
        for zone in (ancienne, self.geometry()):
            page.update(zone.translated(decalage).adjusted(-marge, -marge, marge, marge))


class Page(QWidget):
    """Contenu d'un onglet : une colonne centrée de largeur limitée, sur la lueur du fond.

    La page peint elle-même la lueur, qui défile avec elle : la page est opaque, et Qt peut alors faire défiler
    l'image déjà dessinée au lieu de tout redessiner (défilement fluide, même en plein écran). Elle dessine aussi
    l'ombre des cartes de verre qu'elle contient, juste sous elles.
    """

    LARGEUR_MAX, MARGE = 1000, 32

    def __init__(self) -> None:
        super().__init__(objectName="contenu")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)  # la page couvre tout ce qu'elle occupe
        self.disposition = QVBoxLayout(self)
        self.disposition.setSpacing(16)
        self._marges(self.MARGE)

    def _marges(self, cote: int) -> None:
        self.disposition.setContentsMargins(cote, 14, cote, 28)

    def resizeEvent(self, evenement) -> None:
        cote = max(self.MARGE, (self.width() - self.LARGEUR_MAX) // 2)
        if self.disposition.contentsMargins().left() != cote:
            self._marges(cote)
        super().resizeEvent(evenement)

    def paintEvent(self, evenement) -> None:
        peintre = QPainter(self)
        zone = QRectF(evenement.rect())
        ambiance = self.parentWidget()
        while ambiance is not None and not isinstance(ambiance, Ambiance):
            ambiance = ambiance.parentWidget()
        if ambiance is not None:
            ambiance.peindre_lueur(peintre, zone, self.width())
        else:  # page seule (tests) : un fond uni
            peintre.fillRect(zone, QColor(theme.FOND))
        visible = zone.adjusted(-60, -60, 60, 60)
        for carte in self.findChildren(Verre):
            if not carte.ombre or not carte.isVisible():
                continue
            rect = QRectF(QRect(carte.mapTo(self, QPoint(0, 0)), carte.size()))
            if not rect.intersects(visible):
                continue
            effet = carte.graphicsEffect()  # carte qui apparaît en fondu : son ombre aussi
            peintre.setOpacity(effet.opacity() if isinstance(effet, QGraphicsOpacityEffect) else 1.0)
            dessiner_ombre(peintre, rect, carte.rayon)


# --- Lueur du fond ---

REDUCTION = 4  # la lueur est calculée 4 fois plus petite puis agrandie : elle est si douce que ça ne se voit pas
TRANCHE = 600  # hauteur calculée par tranches : une page qui s'allonge un peu ne fait pas tout recalculer


@cache
def _grain() -> QPixmap:
    """Grain très fin posé sur la lueur : il évite les marches visibles dans les dégradés sombres."""
    cote = 128
    donnees = bytearray()
    for octet in os.urandom(cote * cote):
        alpha = octet % 6
        valeur = alpha if octet & 0x80 else 0  # point clair ou sombre, à peine visible (prémultiplié)
        donnees += bytes((valeur, valeur, valeur, alpha))
    return QPixmap.fromImage(QImage(bytes(donnees), cote, cote, cote * 4,
                                    QImage.Format.Format_ARGB32_Premultiplied).copy())


@lru_cache(maxsize=8)
def _image_lueur(largeur: int, hauteur: int, vue: int, teinte: str, clair: bool) -> QImage:
    """La lueur d'une page de `largeur` x `hauteur`, en petit. `vue` : hauteur visible de la fenêtre, qui place
    les taches de couleur. `clair` fait partie de la clé : les couleurs changent avec le mode."""
    image = QImage(largeur // REDUCTION + 2, hauteur // REDUCTION + 2, QImage.Format.Format_RGB32)
    peintre = QPainter(image)
    peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
    peintre.scale(1 / REDUCTION, 1 / REDUCTION)
    tout = QRectF(0, 0, largeur + 2 * REDUCTION, hauteur + 2 * REDUCTION)
    base = QLinearGradient(0, 0, 0, vue)
    base.setColorAt(0, QColor(theme.FOND))
    base.setColorAt(1, QColor(theme.FOND_BAS))
    peintre.fillRect(tout, base)
    grand = max(largeur, vue * 1.3)
    # Lueur principale derrière le score (sa couleur dit l'état du PC), une autre en haut à droite, une en bas de
    # l'écran ; plus bas dans la page, d'autres plus discrètes : le verre des cartes garde des couleurs partout.
    lueurs = [(0.20 * largeur, 150, 0.62 * grand, theme.LUEURS[teinte], 0.42 if clair else 0.30),
              (0.92 * largeur, 40, 0.50 * grand, theme.LUEUR_2, 0.38 if clair else 0.22),
              (0.35 * largeur, vue + 60, 0.55 * grand, theme.LUEUR_3, 0.24 if clair else 0.10)]
    y, cote = 1.8 * vue, 0
    while y < hauteur + 0.4 * grand:  # puis, en descendant, alternativement à droite et à gauche
        lueurs.append((0.85 * largeur if cote == 0 else 0.15 * largeur, y, 0.45 * grand,
                       theme.LUEUR_2 if cote == 0 else theme.LUEUR_3, 0.26 if clair else 0.14))
        y, cote = y + 0.9 * vue, 1 - cote
    for x, y, rayon, couleur, opacite in lueurs:
        degrade = QRadialGradient(QPointF(x, y), rayon)
        for position, part in ((0, 1.0), (0.35, 0.55), (0.7, 0.15), (1, 0.0)):
            nuance = QColor(couleur)
            nuance.setAlphaF(opacite * part)
            degrade.setColorAt(position, nuance)
        peintre.fillRect(tout, degrade)
    # Haut uni, de la couleur de la barre du haut et de celle de Windows : aucun raccord visible.
    bande = QLinearGradient(0, 0, 0, 56)
    transparent = QColor(theme.FOND)
    transparent.setAlpha(0)
    bande.setColorAt(0, QColor(theme.FOND))
    bande.setColorAt(1, transparent)
    peintre.fillRect(QRectF(0, 0, largeur + 2 * REDUCTION, 56), bande)
    peintre.end()
    return image


class Ambiance(QWidget):
    """Fond de la fenêtre : uni en haut (barre du haut), et la lueur douce sous les pages, dont la teinte
    principale suit la santé du PC. La lueur est peinte par les pages, qui défilent avec elle."""

    # Passage d'une teinte à l'autre : en ETAPES_TEINTE fondus successifs. Chaque étape redessine toute la page ;
    # à chaque image, ce serait trop lourd en plein écran. L'écart de couleur entre deux étapes est si faible que
    # le passage paraît continu.
    DUREE_TEINTE, ETAPES_TEINTE = 800, 10

    def __init__(self, teinte: str = "neutre") -> None:
        super().__init__(objectName="racine")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)  # couvre tout : rien n'est dessiné dessous
        self.teinte, self.ancienne = teinte, teinte
        self.progres = 1.0
        self.defilement = None  # zone de défilement de l'onglet affiché
        self.superpositions: list[QWidget] = []  # annonces : replacées à chaque redimensionnement
        transition = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=self.DUREE_TEINTE,
                                       easingCurve=QEasingCurve.Type.InOutSine)
        transition.valueChanged.connect(self._avancer)
        self.enchainement = QSequentialAnimationGroup(self)  # une attente, puis le passage
        self.attente = self.enchainement.addPause(0)
        self.enchainement.addAnimation(transition)

    def definir_teinte(self, teinte: str, animer: bool = True, attente: int = 0) -> None:
        """`attente` (ms) : le passage commence une fois finies les animations du moment (l'anneau qui se
        remplit) ; ses étapes, qui redessinent toute la page, ne les font pas saccader."""
        if teinte == self.teinte:
            return
        self.ancienne, self.teinte = self.teinte, teinte
        self.enchainement.stop()
        if animer and self.isVisible():
            self.progres = 0.0  # l'ancienne teinte reste affichée pendant l'attente : rien à redessiner
            self.attente.setDuration(attente)
            self.enchainement.start()
        else:
            self.progres = 1.0
            self._repeindre()

    def _avancer(self, progres: float) -> None:
        etape = round(progres * self.ETAPES_TEINTE) / self.ETAPES_TEINTE
        if etape != self.progres:
            self.progres = etape
            self._repeindre()

    def _repeindre(self) -> None:
        for page in self.findChildren(Page):
            page.update()
        self.update()

    def resizeEvent(self, evenement) -> None:
        super().resizeEvent(evenement)
        for superposition in self.superpositions:
            superposition.placer()

    def peindre_lueur(self, peintre: QPainter, zone: QRectF, largeur: int) -> None:
        """Peint la lueur dans `zone` (coordonnées d'une page : 0 en haut de la page)."""
        vue = max(400, self.height() - theme.HAUTEUR_BARRE)
        hauteur = (int(zone.bottom()) // TRANCHE + 1) * TRANCHE
        peintre.save()
        peintre.setClipRect(zone)
        peintre.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        cible = QRectF(0, 0, (largeur // REDUCTION + 2) * REDUCTION, (hauteur // REDUCTION + 2) * REDUCTION)
        if self.progres < 1:  # changement de teinte : l'ancienne s'efface sous la nouvelle
            peintre.drawImage(cible, _image_lueur(largeur, hauteur, vue, self.ancienne, theme.CLAIR))
            peintre.setOpacity(self.progres)
        peintre.drawImage(cible, _image_lueur(largeur, hauteur, vue, self.teinte, theme.CLAIR))
        peintre.setOpacity(1.0)
        peintre.drawTiledPixmap(zone, _grain(), QPointF(zone.x() % 128, zone.y() % 128))  # grain fixé à la page
        peintre.restore()

    def paintEvent(self, evenement) -> None:
        peintre = QPainter(self)
        peintre.fillRect(evenement.rect(), QColor(theme.FOND))
        # Sous la barre (à côté de la page, derrière la barre de défilement) : la lueur de la page affichée.
        if self.defilement is None or self.defilement.widget() is None:
            return
        page = self.defilement.widget()
        origine = page.mapFrom(self, QPoint(0, 0))
        zone = QRectF(evenement.rect()).intersected(QRectF(0, theme.HAUTEUR_BARRE, self.width(), self.height()))
        if zone.isEmpty():
            return
        peintre.translate(-origine.x(), -origine.y())
        self.peindre_lueur(peintre, zone.translated(origine.x(), origine.y()), page.width())
