"""Thème de l'interface : couleurs, polices, icônes et feuille de style.

Tout l'aspect visuel est réglé ici. Polices et icônes sont celles de Windows 11
(Segoe UI Variable, Segoe Fluent Icons) : rien à installer en plus.
Couleurs claires ou sombres : celles choisies avec le bouton de la fenêtre, sinon celles de Windows.
"""

import json
import winreg
from functools import cache
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap

from journal import dossier_par_defaut


def fichier_reglages() -> Path:
    return dossier_par_defaut() / "reglages.json"


def mode_choisi() -> bool | None:
    """Mode choisi avec le bouton clair/sombre (True = clair), ou None s'il n'a jamais servi."""
    try:
        reglages = json.loads(fichier_reglages().read_text(encoding="utf-8"))
        return {"clair": True, "sombre": False}.get(reglages.get("theme"))
    except (OSError, ValueError, AttributeError):  # absent ou abîmé : on suit Windows
        return None


def enregistrer_mode(clair: bool) -> None:
    chemin = fichier_reglages()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps({"theme": "clair" if clair else "sombre"}), encoding="utf-8")


def windows_en_clair() -> bool:
    """Vrai si Windows est en mode clair pour les applications (Paramètres > Personnalisation > Couleurs)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as cle:
            return winreg.QueryValueEx(cle, "AppsUseLightTheme")[0] == 1
    except OSError:  # réglage absent : thème sombre, celui d'origine de l'application
        return False


_choix = mode_choisi()
CLAIR = windows_en_clair() if _choix is None else _choix


def _selon_mode(sombre: str, clair: str) -> str:
    return clair if CLAIR else sombre


# --- Couleurs (sombre, clair) ---
FOND = _selon_mode("#0f1117", "#f3f4f7")
SURFACE = _selon_mode("#171a21", "#ffffff")
SURFACE_2 = _selon_mode("#1e222b", "#eef0f4")   # éléments posés sur une carte (tableaux, survol)
BORDURE = _selon_mode("#262b36", "#dcdfe6")
TEXTE = _selon_mode("#e8eaf0", "#1b1f27")
TEXTE_2 = _selon_mode("#a3abba", "#4b5363")     # texte secondaire
TEXTE_3 = _selon_mode("#6f7789", "#5f6777")     # légendes, repères
ACCENT = _selon_mode("#3b6cf6", "#2f5fe0")      # bouton principal : contraste suffisant avec le texte blanc
ACCENT_SURVOL = _selon_mode("#5080f7", "#2752c9")
ACCENT_APPUI = _selon_mode("#315ddb", "#2148b0")
ACCENT_CLAIR = _selon_mode("#7aa2ff", "#2f5fe0")  # liens, courbe du graphique
HEROS = _selon_mode("#1b2030", "#e8eefc")       # début du dégradé de la zone du score
SURVOL = _selon_mode("#262b36", "#e4e7ed")
SURVOL_BORDURE = _selon_mode("#323846", "#c9ced8")
PRINCIPAL_INACTIF = _selon_mode("#253463", "#b9c8f2")
PRINCIPAL_INACTIF_TEXTE = _selon_mode("#a9b8e8", "#f5f7ff")
LIGNE_ALTERNEE = _selon_mode("#1b1f27", "#f6f7f9")
SELECTION = _selon_mode("#2a3550", "#dbe5ff")
POIGNEE = _selon_mode("#2c3240", "#c9ced8")      # barres de défilement
POIGNEE_SURVOL = _selon_mode("#3a4152", "#aeb4c0")

# Couleurs d'état, réservées au niveau de santé (toujours accompagnées d'un texte).
NIVEAUX = {"vert": _selon_mode("#34d399", "#15803d"), "orange": _selon_mode("#fbbf24", "#b45309"),
           "rouge": _selon_mode("#f87171", "#dc2626"), "gris": TEXTE_3}


def rgba(couleur: str, alpha: int) -> str:
    """Couleur semi-transparente pour la feuille de style (alpha de 0 à 255)."""
    c = QColor(couleur)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"

# --- Polices ---
TITRE = ("Segoe UI Variable Display", "Segoe UI")
CORPS = ("Segoe UI Variable Text", "Segoe UI")
ICONES = ("Segoe Fluent Icons", "Segoe MDL2 Assets")  # Windows 11, sinon Windows 10

# Codes des icônes (communs à Segoe Fluent Icons et Segoe MDL2 Assets).
ICONE = {
    "logo": "", "demarrage": "", "disque": "", "ressources": "",
    "fichiers": "", "redemarrage": "", "batterie": "", "alimentation": "",
    "bouclier": "", "conseil": "", "historique": "",
    "analyser": "", "copier": "", "enregistrer": "", "effacer": "", "ouvrir": "", "soleil": "", "lune": "",
    "deplier": "", "replier": "", "erreur": "",
}


@cache
def famille(choix: tuple[str, ...]) -> str:
    """Première police installée parmi `choix` (la dernière si aucune ne l'est).

    Une seule famille est donnée à Qt : avec une liste (setFamilies), Qt charge toute la base
    des polices du système, soit environ 45 Mo de mémoire en plus.
    """
    return next((nom for nom in choix if QFontDatabase.hasFamily(nom)), choix[-1])


def police(taille: float, poids: QFont.Weight = QFont.Weight.Normal, titre: bool = False) -> QFont:
    """Police du thème, avec repli sur Segoe UI si Segoe UI Variable manque."""
    resultat = QFont(famille(TITRE if titre else CORPS))
    resultat.setPointSizeF(taille)
    resultat.setWeight(poids)
    return resultat


def niveau_ratio(ratio: float) -> str:
    """Niveau de couleur d'une partie selon la part de points gardés."""
    return "vert" if ratio >= 0.8 else "orange" if ratio >= 0.5 else "rouge"


@cache  # gardée en mémoire : redessinée à chaque défilement de la fenêtre, sinon
def pixmap_icone(nom: str, couleur: str, taille: int = 16, ratio_ecran: float = 2.0) -> QPixmap:
    """Dessine une icône de la police Segoe dans une image (nette sur les écrans haute densité)."""
    image = QPixmap(round(taille * ratio_ecran), round(taille * ratio_ecran))
    image.setDevicePixelRatio(ratio_ecran)
    image.fill(Qt.GlobalColor.transparent)
    peintre = QPainter(image)
    peintre.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    fonte = QFont(famille(ICONES))
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
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {HEROS}, stop:1 {SURFACE}); }}
QFrame#conseil {{ background: {SURFACE}; border: 1px solid {BORDURE}; border-radius: 12px; }}

QLabel#pastille {{ border-radius: 10px; padding: 2px 10px; font-weight: 600; }}
QLabel#pastille[niveau="vert"] {{ color: {NIVEAUX["vert"]}; background: {rgba(NIVEAUX["vert"], 31)}; }}
QLabel#pastille[niveau="orange"] {{ color: {NIVEAUX["orange"]}; background: {rgba(NIVEAUX["orange"], 31)}; }}
QLabel#pastille[niveau="rouge"] {{ color: {NIVEAUX["rouge"]}; background: {rgba(NIVEAUX["rouge"], 31)}; }}
QLabel#pastille[niveau="gris"] {{ color: {TEXTE_2}; background: {SURFACE_2}; }}

QPushButton {{ background: {SURFACE_2}; color: {TEXTE}; border: 1px solid {BORDURE}; border-radius: 9px;
               padding: 8px 16px; }}
QPushButton:hover {{ background: {SURVOL}; border-color: {SURVOL_BORDURE}; }}
QPushButton:pressed {{ background: {SURFACE}; }}
QPushButton:disabled {{ color: {TEXTE_3}; background: {SURFACE}; border-color: {SURFACE_2}; }}
QPushButton:focus {{ border-color: {ACCENT_CLAIR}; }}
QPushButton#principal {{ background: {ACCENT}; color: white; border: none; border-radius: 12px;
                         padding: 13px 28px; font-weight: 600; }}
QPushButton#principal:hover {{ background: {ACCENT_SURVOL}; }}
QPushButton#principal:pressed {{ background: {ACCENT_APPUI}; }}
QPushButton#principal:disabled {{ background: {PRINCIPAL_INACTIF}; color: {PRINCIPAL_INACTIF_TEXTE}; }}
QPushButton#principal:focus {{ border: 2px solid {ACCENT_CLAIR}; }}
QPushButton#lien, QPushButton#discret {{ background: transparent; border: none; padding: 4px 6px; }}
QPushButton#lien {{ color: {ACCENT_CLAIR}; text-align: left; }}
QPushButton#discret {{ color: {TEXTE_2}; }}
QPushButton#lien:hover, QPushButton#discret:hover {{ color: {TEXTE}; background: {SURFACE_2}; border-radius: 7px; }}

QTreeWidget {{ background: {SURFACE_2}; border: none; border-radius: 10px; padding: 4px;
               alternate-background-color: {LIGNE_ALTERNEE}; outline: 0; }}
QTreeWidget::item {{ padding: 4px 2px; border: none; }}
QTreeWidget::item:selected {{ background: {SELECTION}; color: {TEXTE}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {SURFACE_2}; color: {TEXTE_3}; border: none;
                        border-bottom: 1px solid {BORDURE}; padding: 6px 4px; font-weight: 600; }}

QProgressBar {{ border: none; background: {SURFACE_2}; max-height: 4px; border-radius: 2px; }}
QProgressBar::chunk {{ background: {ACCENT_CLAIR}; border-radius: 2px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {POIGNEE}; border-radius: 3px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {POIGNEE_SURVOL}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QStatusBar {{ background: {FOND}; color: {TEXTE_3}; border-top: 1px solid {BORDURE}; }}
QStatusBar::item {{ border: none; }}
QToolTip {{ background: {SURFACE_2}; color: {TEXTE}; border: 1px solid {BORDURE}; border-radius: 6px;
            padding: 4px 8px; }}
QMessageBox {{ background: {SURFACE}; }}
QMessageBox QLabel {{ color: {TEXTE}; }}
"""
