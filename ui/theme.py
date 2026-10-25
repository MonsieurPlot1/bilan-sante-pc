"""Thème de l'interface : couleurs, matières (verre dépoli), polices, icônes et feuille de style.

Tout l'aspect visuel est réglé ici, dans l'esprit des applications d'Apple : du verre dépoli posé sur une
lueur douce, du texte en trois niveaux de gris, une seule couleur d'action (le bleu).
Polices et icônes : celles de Windows 11 (Segoe UI Variable, Segoe Fluent Icons), rien à installer en plus.
Segoe UI Variable plutôt qu'une police livrée avec l'application : plus nette sur un écran à 100 %, et plus
rapide à dessiner (mesuré : des dépliages et des redimensionnements plus fluides).
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


def voile(couleur: str, opacite: float) -> str:
    """La couleur avec cette opacité (0 à 1), au format « #AARRGGBB » que QColor comprend."""
    c = QColor(couleur)
    return f"#{round(opacite * 255):02x}{c.red():02x}{c.green():02x}{c.blue():02x}"


def rgba(couleur: str, alpha: int | None = None) -> str:
    """Couleur pour la feuille de style : `alpha` de 0 à 255, sinon celle de la couleur (« #AARRGGBB »)."""
    c = QColor(couleur)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {c.alpha() if alpha is None else alpha})"


BLANC, NOIR = "#ffffff", "#000000"

# --- Couleurs (sombre, clair) ---
# Fond de la fenêtre, sous la lueur : FOND en haut (même couleur que la barre de titre), FOND_BAS en bas.
FOND = _selon_mode("#12151f", "#eef0f6")
FOND_BAS = _selon_mode("#0b0d14", "#e5e8f1")
BORD_FENETRE = _selon_mode("#2c303c", "#c9ced9")  # liseré de la fenêtre dessiné par Windows 11
# Texte en trois niveaux, tous lisibles sur le verre (contraste d'au moins 4,5:1).
TEXTE = _selon_mode("#f5f5f7", "#1d1d1f")
TEXTE_2 = _selon_mode("#ababb1", "#5e5e64")      # texte secondaire
TEXTE_3 = _selon_mode("#98989e", "#6e6e73")      # légendes, repères
# Une seule couleur d'action, comme chez Apple. Bouton principal : texte blanc, contraste 4,7:1.
ACCENT = "#0071e3"
ACCENT_SURVOL = "#0a7cf0"
ACCENT_APPUI = "#0064ca"
ACCENT_CLAIR = _selon_mode("#2997ff", "#0066cc")  # liens, courbe du graphique

# Verre dépoli des cartes : un voile blanc plus marqué en haut, et un filet de lumière sur le bord.
VERRE_HAUT = _selon_mode(voile(BLANC, 0.085), voile(BLANC, 0.72))
VERRE_BAS = _selon_mode(voile(BLANC, 0.045), voile(BLANC, 0.50))
REFLET_HAUT = _selon_mode(voile(BLANC, 0.20), voile(BLANC, 1.0))
REFLET_BAS = _selon_mode(voile(BLANC, 0.05), voile(BLANC, 0.55))
CONTOUR = _selon_mode(voile(NOIR, 0.30), voile("#1d2440", 0.07))  # trait extérieur, qui détache la carte
SURFACE = _selon_mode("#232633", "#f6f7fa")  # couleur moyenne d'une carte : anneau autour des points du graphique
OMBRE = _selon_mode(voile(NOIR, 0.30), voile("#26305a", 0.09))
# Verre des fenêtres de confirmation, des annonces et des infobulles, et de la barre du haut quand la page
# défile dessous.
VERRE_FEUILLE = _selon_mode(voile("#262a36", 0.92), voile("#fbfbfd", 0.94))
VERRE_BARRE = _selon_mode(voile(FOND, 0.38), voile(FOND, 0.42))
VOILE_FEUILLE = _selon_mode(voile(NOIR, 0.35), voile("#1d2440", 0.16))  # assombrit la fenêtre derrière

# Éléments posés sur le verre : boutons secondaires, pistes des barres, survol des lignes.
REMPLI = _selon_mode(voile(BLANC, 0.09), voile(NOIR, 0.05))
REMPLI_SURVOL = _selon_mode(voile(BLANC, 0.14), voile(NOIR, 0.08))
REMPLI_APPUI = _selon_mode(voile(BLANC, 0.06), voile(NOIR, 0.11))
SURVOL_LIGNE = _selon_mode(voile(BLANC, 0.055), voile(NOIR, 0.04))
SEPARATEUR = _selon_mode(voile(BLANC, 0.08), voile(NOIR, 0.08))
CURSEUR = _selon_mode(voile(BLANC, 0.17), BLANC)  # pastille qui glisse dans les sélecteurs
POIGNEE = _selon_mode(voile(BLANC, 0.22), voile(NOIR, 0.22))  # barres de défilement
POIGNEE_SURVOL = _selon_mode(voile(BLANC, 0.38), voile(NOIR, 0.38))

# Couleurs d'état, réservées au niveau de santé (toujours accompagnées d'un texte).
# NIVEAUX : pour le texte (lisible sur le verre) ; VIFS : pour l'anneau du score et les barres.
NIVEAUX = {"vert": _selon_mode("#30d158", "#1e7b34"), "orange": _selon_mode("#ff9f0a", "#c93400"),
           "rouge": _selon_mode("#ff6961", "#d70015"), "gris": TEXTE_3}
VIFS = {"vert": _selon_mode("#30d158", "#34c759"), "orange": _selon_mode("#ff9f0a", "#ff9500"),
        "rouge": _selon_mode("#ff453a", "#ff3b30"), "gris": TEXTE_3}

# Lueur du fond : la teinte principale suit la santé du PC (bleu avant toute analyse).
LUEURS = {"neutre": _selon_mode("#2f6bff", "#7aa7ff"),
          **{niveau: VIFS[niveau] for niveau in ("vert", "orange", "rouge")}}
LUEUR_2 = _selon_mode("#5e5ce6", "#a9a6ff")  # indigo, en haut à droite
LUEUR_3 = _selon_mode("#40c8e0", "#8fe3f0")  # bleu-vert, discret, en bas

# Teintes des icônes et des catégories du stockage (jamais les couleurs d'état). Ordre et nuances vérifiés
# pour rester distincts deux à deux, y compris pour les daltoniens.
TEINTES = {"bleu": _selon_mode("#3987e5", "#2a78d6"), "magenta": _selon_mode("#d55181", "#e0679a"),
           "violet": _selon_mode("#9085e9", "#6250d6"), "aqua": _selon_mode("#199e70", "#18a473"),
           "gris": _selon_mode("#7c7c84", "#8e8e93"), "gris_clair": _selon_mode("#5c5c66", "#a8a8ae")}


def niveau_ratio(ratio: float) -> str:
    """Niveau de couleur d'une partie selon la part de points gardés."""
    return "vert" if ratio >= 0.8 else "orange" if ratio >= 0.5 else "rouge"


# --- Polices ---
TITRE = ("Segoe UI Variable Display", "Segoe UI")  # dessin serré des grands textes
CORPS = ("Segoe UI Variable Text", "Segoe UI")
ICONES = ("Segoe Fluent Icons", "Segoe MDL2 Assets")  # Windows 11, sinon Windows 10

# Icône de l'application (barre de titre, barre des tâches, boîtes de dialogue). build.bat la copie au même
# endroit dans le .exe, donc ce chemin marche aussi une fois compilé.
ICONE_APPLICATION = Path(__file__).parent.parent / "assets" / "icon.ico"

# Codes des icônes (communs à Segoe Fluent Icons et Segoe MDL2 Assets).
ICONE = {
    "demarrage": "", "disque": "", "ressources": "",
    "fichiers": "", "redemarrage": "", "batterie": "", "alimentation": "",
    "bouclier": "", "conseil": "", "historique": "",
    "analyser": "", "copier": "", "enregistrer": "", "effacer": "", "ouvrir": "",
    "valide": "", "soleil": "", "lune": "", "deplier": "", "replier": "",
    "erreur": "", "info": "", "avertissement": "",
    # Onglets, éléments et catégories de la page Stockage.
    "bilan": "", "stockage": "", "dossier": "", "fichier": "",
    "systeme": "", "applications": "", "jeux": "", "videos": "", "photos": "",
    "musique": "", "documents": "", "archives": "", "temporaires": "",
    "corbeille": "", "sauvegardes": "", "autres": "",
    # Page Connexion : compteur de vitesse, téléchargement, envoi, chronomètre (ping).
    "connexion": "", "telechargement": "", "envoi": "", "ping": "",
}


@cache
def famille(choix: tuple[str, ...]) -> str:
    """Première police installée parmi `choix` (la dernière si aucune ne l'est).

    Une seule famille est donnée à Qt : avec une liste (setFamilies), Qt charge toute la base
    des polices du système, soit environ 45 Mo de mémoire en plus.
    """
    return next((nom for nom in choix if QFontDatabase.hasFamily(nom)), choix[-1])


# Échelle typographique : peu de tailles et de graisses, toujours les mêmes, comme chez Apple. Elle rend
# l'interface cohérente, et Qt a moins de polices à préparer (chacune coûte la première fois qu'elle sert).
# Style : (taille en points, graisse, titre, chiffres). `titre` : dessin serré des grands textes (Segoe UI
# Variable Display) ; `chiffres` : chiffres de même largeur, pour ceux qui s'alignent ou défilent.
ECHELLE = {
    "score": (36, QFont.Weight.Bold, True, True),        # le score dans l'anneau
    "grand": (24, QFont.Weight.Bold, True, True),        # espace utilisé du disque
    "titre": (17, QFont.Weight.Bold, True, False),       # phrase sous le score
    "section": (13.5, QFont.Weight.Bold, True, False),   # titres de section
    "carte": (11.5, QFont.Weight.DemiBold, True, False), # titres de carte, de confirmation, nom de l'application
    "corps": (10, QFont.Weight.Normal, False, False),    # texte courant
    "fort": (10, QFont.Weight.DemiBold, False, False),   # noms des éléments, bouton principal
    "chiffres": (10, QFont.Weight.DemiBold, False, True),  # tailles en colonne
    "legende": (9, QFont.Weight.Normal, False, False),   # chemins, explications, repères
    "legende_forte": (9, QFont.Weight.DemiBold, False, False),  # pastilles, valeurs des légendes
}


def police(style: str = "corps") -> QFont:
    """Police d'un style de l'échelle typographique."""
    taille, poids, titre, chiffres = ECHELLE[style]
    resultat = QFont(famille(TITRE if titre else CORPS))
    resultat.setPointSizeF(taille)
    resultat.setWeight(poids)
    if chiffres:
        resultat.setFeature(QFont.Tag("tnum"), 1)
    return resultat


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


HAUTEUR_BARRE = 50  # barre du haut (logo, onglets, mode), sous la barre de titre de Windows

# Infobulles au survol, toutes dessinées par Infobulle (ui/widgets.py), pas par la feuille de style : le verre bleu
# nuit des annonces (VERRE_FEUILLE), bordé comme les cartes, texte clair (TEXTE) dans la police des légendes.
POLICE_INFOBULLE = "legende"
RAYON_INFOBULLE = 12  # comme les lignes de liste
MARGES_INFOBULLE = (12, 7)  # marge intérieure : à gauche et à droite, en haut et en bas
MARGES_TEXTE_COMPLET = (8, 3)  # posée par-dessus un texte coupé : juste de quoi l'entourer, sans cacher ses voisins

STYLE = f"""
QWidget {{ color: {TEXTE}; }}
QMainWindow, QStackedWidget, QScrollArea, QWidget#qt_scrollarea_viewport {{
    background: transparent; border: none; }}
QLabel {{ background: transparent; }}
QLabel#secondaire {{ color: {TEXTE_2}; }}
QLabel#discret {{ color: {TEXTE_3}; }}
QLabel#erreur {{ color: {NIVEAUX["rouge"]}; }}

QLabel#pastille {{ border-radius: 9px; padding: 3px 10px; font-weight: 600; }}
QLabel#pastille[niveau="vert"] {{ color: {NIVEAUX["vert"]}; background: {rgba(VIFS["vert"], 38)}; }}
QLabel#pastille[niveau="orange"] {{ color: {NIVEAUX["orange"]}; background: {rgba(VIFS["orange"], 38)}; }}
QLabel#pastille[niveau="rouge"] {{ color: {NIVEAUX["rouge"]}; background: {rgba(VIFS["rouge"], 38)}; }}
QLabel#pastille[niveau="gris"] {{ color: {TEXTE_2}; background: {rgba(REMPLI)}; }}

QFrame#ligne {{ background: transparent; border-radius: 12px; }}
QFrame#ligne:hover, QFrame#ligne:focus {{ background: {rgba(SURVOL_LIGNE)}; }}

QPushButton {{ background: {rgba(REMPLI)}; color: {TEXTE}; border: 1px solid transparent; border-radius: 14px;
               padding: 7px 16px; min-height: 18px; font-weight: 500; }}
QPushButton:hover {{ background: {rgba(REMPLI_SURVOL)}; }}
QPushButton:pressed {{ background: {rgba(REMPLI_APPUI)}; }}
QPushButton:disabled {{ color: {TEXTE_3}; background: {rgba(REMPLI_APPUI)}; }}
QPushButton:focus {{ border-color: {ACCENT_CLAIR}; }}
QPushButton#principal {{ background: {ACCENT}; color: white; border-radius: 17px; padding: 9px 22px; min-height: 20px;
                         font-weight: 600; }}
QPushButton#principal:hover {{ background: {ACCENT_SURVOL}; }}
QPushButton#principal:pressed {{ background: {ACCENT_APPUI}; }}
QPushButton#principal:disabled {{ background: {rgba(ACCENT, 110)}; color: {rgba(BLANC, 200)}; }}
QPushButton#principal:focus {{ border-color: {rgba(BLANC, 200)}; }}
QPushButton#destructif {{ background: {VIFS["rouge"]}; color: white; font-weight: 600; }}
QPushButton#destructif:hover {{ background: {QColor(VIFS["rouge"]).lighter(110).name()}; }}
QPushButton#destructif:pressed {{ background: {QColor(VIFS["rouge"]).darker(110).name()}; }}
QPushButton#destructif:focus {{ border-color: {rgba(BLANC, 200)}; }}
QPushButton#lien, QPushButton#discret, QPushButton#supprimer {{ background: transparent; border-radius: 9px;
                                                               padding: 4px 8px; font-weight: 500; }}
QPushButton#lien {{ color: {ACCENT_CLAIR}; text-align: left; }}
QPushButton#discret, QPushButton#supprimer {{ color: {TEXTE_2}; }}
QPushButton#lien:hover, QPushButton#discret:hover {{ background: {rgba(SURVOL_LIGNE)}; }}
QPushButton#discret:hover {{ color: {TEXTE}; }}
QPushButton#supprimer:hover, QPushButton#supprimer:focus {{ color: {NIVEAUX["rouge"]};
                                                            background: {rgba(VIFS["rouge"], 30)}; }}
QPushButton#lien:disabled, QPushButton#discret:disabled, QPushButton#supprimer:disabled {{
    color: {TEXTE_3}; background: transparent; }}
QPushButton#rond {{ border-radius: 17px; padding: 0; min-width: 34px; max-width: 34px; min-height: 34px;
                    max-height: 34px; }}
QPushButton#segment {{ background: transparent; color: {TEXTE_2}; border-radius: 12px; padding: 6px 18px;
                       font-weight: 600; }}
QPushButton#segment:hover {{ color: {TEXTE}; }}
QPushButton#segment:checked {{ color: {TEXTE}; }}
QPushButton#segment:disabled {{ color: {TEXTE_3}; }}

QTreeWidget {{ background: transparent; border: none; outline: 0; }}
QTreeWidget::item {{ padding: 6px 2px; border: none; border-bottom: 1px solid {rgba(SEPARATEUR)}; }}
QTreeWidget::item:selected {{ background: {rgba(SURVOL_LIGNE)}; color: {TEXTE}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: transparent; color: {TEXTE_3}; border: none;
                        border-bottom: 1px solid {rgba(SEPARATEUR)}; padding: 4px 2px 6px 2px; font-weight: 600; }}

QProgressBar {{ border: none; background: {rgba(REMPLI)}; max-height: 6px; min-height: 6px; border-radius: 3px; }}
QProgressBar::chunk {{ background: {ACCENT_CLAIR}; border-radius: 3px; }}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 4px 2px 6px 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle {{ background: {rgba(POIGNEE)}; border-radius: 4px; min-height: 32px; min-width: 32px; }}
QScrollBar::handle:hover {{ background: {rgba(POIGNEE_SURVOL)}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
"""
