"""Thème de l'interface : couleurs, polices, icônes et feuille de style.

Tout l'aspect visuel est réglé ici. Polices et icônes sont celles de Windows 11
(Segoe UI Variable, Segoe Fluent Icons) : rien à installer en plus.
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

# --- Couleurs ---
FOND = "#0f1117"
SURFACE = "#171a21"
SURFACE_2 = "#1e222b"   # éléments posés sur une carte (tableaux, survol)
BORDURE = "#262b36"
TEXTE = "#e8eaf0"
TEXTE_2 = "#a3abba"     # texte secondaire
TEXTE_3 = "#6f7789"     # légendes, repères
ACCENT = "#3b6cf6"      # bouton principal : contraste suffisant avec le texte blanc
ACCENT_SURVOL = "#5080f7"
ACCENT_CLAIR = "#7aa2ff"  # liens, courbe du graphique

# Couleurs d'état, réservées au niveau de santé (toujours accompagnées d'un texte).
NIVEAUX = {"vert": "#34d399", "orange": "#fbbf24", "rouge": "#f87171", "gris": "#6f7789"}

# --- Polices ---
TITRE = ["Segoe UI Variable Display", "Segoe UI"]
CORPS = ["Segoe UI Variable Text", "Segoe UI"]
ICONES = ["Segoe Fluent Icons", "Segoe MDL2 Assets"]  # Windows 11, sinon Windows 10

# Codes des icônes (communs à Segoe Fluent Icons et Segoe MDL2 Assets).
ICONE = {
    "logo": "", "demarrage": "", "disque": "", "ressources": "",
    "batterie": "", "bouclier": "", "conseil": "", "historique": "",
    "analyser": "", "copier": "", "enregistrer": "", "effacer": "",
    "deplier": "", "replier": "", "erreur": "",
}


def police(taille: float, poids: QFont.Weight = QFont.Weight.Normal, titre: bool = False) -> QFont:
    """Police du thème, avec repli sur Segoe UI si Segoe UI Variable manque."""
    resultat = QFont()
    resultat.setFamilies(TITRE if titre else CORPS)
    resultat.setPointSizeF(taille)
    resultat.setWeight(poids)
    return resultat


def niveau_ratio(ratio: float) -> str:
    """Niveau de couleur d'une partie selon la part de points gardés."""
    return "vert" if ratio >= 0.8 else "orange" if ratio >= 0.5 else "rouge"


def pixmap_icone(nom: str, couleur: str, taille: int = 16, ratio_ecran: float = 2.0) -> QPixmap:
    """Dessine une icône de la police Segoe dans une image (nette sur les écrans haute densité)."""
    image = QPixmap(round(taille * ratio_ecran), round(taille * ratio_ecran))
    image.setDevicePixelRatio(ratio_ecran)
    image.fill(Qt.GlobalColor.transparent)
    peintre = QPainter(image)
    peintre.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    fonte = QFont()
    fonte.setFamilies(ICONES)
    fonte.setPixelSize(taille)
    peintre.setFont(fonte)
    peintre.setPen(QColor(couleur))
    peintre.drawText(QRectF(0, 0, taille, taille), Qt.AlignmentFlag.AlignCenter, ICONE[nom])
    peintre.end()
    return image


def icone(nom: str, couleur: str = TEXTE, taille: int = 16) -> QIcon:
    resultat = QIcon(pixmap_icone(nom, couleur, taille))
    resultat.addPixmap(pixmap_icone(nom, TEXTE_3, taille), QIcon.Mode.Disabled)
    return resultat


STYLE = f"""
QMainWindow, QScrollArea, QWidget#contenu {{ background: {FOND}; }}
QWidget {{ color: {TEXTE}; }}
QLabel {{ background: transparent; }}
QLabel#secondaire {{ color: {TEXTE_2}; }}
QLabel#discret {{ color: {TEXTE_3}; }}
QLabel#section {{ color: {TEXTE_2}; font-weight: 600; letter-spacing: 1px; }}
QLabel#version {{ color: {TEXTE_2}; background: {SURFACE_2}; border: 1px solid {BORDURE};
                  border-radius: 9px; padding: 1px 8px; }}
QLabel#erreur {{ color: {NIVEAUX["rouge"]}; }}

QFrame#carte {{ background: {SURFACE}; border: 1px solid {BORDURE}; border-radius: 14px; }}
QFrame#heros {{ border: 1px solid {BORDURE}; border-radius: 18px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1b2030, stop:1 {SURFACE}); }}
QFrame#conseil {{ background: {SURFACE}; border: 1px solid {BORDURE}; border-radius: 12px; }}

QLabel#pastille {{ border-radius: 10px; padding: 2px 10px; font-weight: 600; }}
QLabel#pastille[niveau="vert"] {{ color: {NIVEAUX["vert"]}; background: rgba(52, 211, 153, 31); }}
QLabel#pastille[niveau="orange"] {{ color: {NIVEAUX["orange"]}; background: rgba(251, 191, 36, 31); }}
QLabel#pastille[niveau="rouge"] {{ color: {NIVEAUX["rouge"]}; background: rgba(248, 113, 113, 31); }}
QLabel#pastille[niveau="gris"] {{ color: {TEXTE_2}; background: {SURFACE_2}; }}

QPushButton {{ background: {SURFACE_2}; color: {TEXTE}; border: 1px solid {BORDURE}; border-radius: 9px;
               padding: 8px 16px; }}
QPushButton:hover {{ background: #262b36; border-color: #323846; }}
QPushButton:pressed {{ background: {SURFACE}; }}
QPushButton:disabled {{ color: {TEXTE_3}; background: {SURFACE}; border-color: {SURFACE_2}; }}
QPushButton:focus {{ border-color: {ACCENT_CLAIR}; }}
QPushButton#principal {{ background: {ACCENT}; color: white; border: none; border-radius: 12px;
                         padding: 13px 28px; font-weight: 600; }}
QPushButton#principal:hover {{ background: {ACCENT_SURVOL}; }}
QPushButton#principal:pressed {{ background: #315ddb; }}
QPushButton#principal:disabled {{ background: #253463; color: #a9b8e8; }}
QPushButton#principal:focus {{ border: 2px solid {ACCENT_CLAIR}; }}
QPushButton#lien, QPushButton#discret {{ background: transparent; border: none; padding: 4px 6px; }}
QPushButton#lien {{ color: {ACCENT_CLAIR}; text-align: left; }}
QPushButton#discret {{ color: {TEXTE_2}; }}
QPushButton#lien:hover, QPushButton#discret:hover {{ color: {TEXTE}; background: {SURFACE_2}; border-radius: 7px; }}

QTreeWidget {{ background: {SURFACE_2}; border: none; border-radius: 10px; padding: 4px;
               alternate-background-color: #1b1f27; outline: 0; }}
QTreeWidget::item {{ padding: 4px 2px; border: none; }}
QTreeWidget::item:selected {{ background: #2a3550; color: {TEXTE}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {SURFACE_2}; color: {TEXTE_3}; border: none;
                        border-bottom: 1px solid {BORDURE}; padding: 6px 4px; font-weight: 600; }}

QProgressBar {{ border: none; background: {SURFACE_2}; max-height: 4px; border-radius: 2px; }}
QProgressBar::chunk {{ background: {ACCENT_CLAIR}; border-radius: 2px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: #2c3240; border-radius: 3px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: #3a4152; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QStatusBar {{ background: {FOND}; color: {TEXTE_3}; border-top: 1px solid {BORDURE}; }}
QStatusBar::item {{ border: none; }}
QToolTip {{ background: {SURFACE_2}; color: {TEXTE}; border: 1px solid {BORDURE}; border-radius: 6px;
            padding: 4px 8px; }}
QMessageBox {{ background: {SURFACE}; }}
QMessageBox QLabel {{ color: {TEXTE}; }}
"""
