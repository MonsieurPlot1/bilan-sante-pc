"""Page Stockage : ce qui prend de la place sur un disque, classé en 12 catégories, et les doublons (PySide6).

Les boutons « Afficher » ouvrent seulement l'Explorateur. Seule action qui modifie le PC : « Supprimer »,
sur un fichier ou un dossier de l'analyse, le supprime définitivement après confirmation (jamais ce qui
casserait Windows ou le profil, voir stockage.supprimable).
"""

import logging
import os
import subprocess
import threading
from contextlib import nullcontext
from datetime import datetime
from typing import Callable

import psutil
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QThread, QVariantAnimation, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from modules import disque, doublons, fichiers, stockage
from modules.disque import taille_lisible
from ui import theme
from ui.analyse import AIDE, arriere_plan
from ui.verre import Page, Verre
from ui.widgets import (BarreEmpilee, BarreScore, Feuille, Legende, Segmente, TuileIcone, apparaitre, bouton,
                        etiquette_couleur,
                        pastille, pied_de_page, repolir, titre_section)

journal = logging.getLogger(__name__)

NB_PLUS_GROS = 8  # éléments de « Ce qui prend le plus de place »
NB_PAR_CATEGORIE = 8  # éléments montrés quand une catégorie est dépliée
HAUTEUR_LIBRE = 16777215  # QWIDGETSIZE_MAX : plus de limite de hauteur
LARGEUR_CHIFFRES = 96  # colonne taille et part du disque (« moins de 1 % »)

# Remplissage du disque : mot affiché à côté de la barre (la couleur n'est jamais seule).
ETATS = {"vert": "Assez de place", "orange": "Bien rempli", "rouge": "Presque plein"}

# Parts de la barre du disque : des groupes de catégories, chacun avec sa teinte (toujours la même, dans cet
# ordre : deux parts voisines restent distinctes, y compris pour les daltoniens).
GROUPES = [("Système", "gris", ("systeme",)), ("Applications", "bleu", ("applications",)),
           ("Jeux", "magenta", ("jeux",)), ("Photos, vidéos et musique", "violet", ("videos", "photos", "musique")),
           ("Documents et archives", "aqua", ("documents", "archives")),
           ("Autres", "gris_clair", ("temporaires", "corbeille", "sauvegardes", "autres"))]
TEINTE_CATEGORIE = {cle: teinte for _nom, teinte, cles in GROUPES for cle in cles}

TEXTE_DOUBLONS = ("Cherche les fichiers et les dossiers en double dans tes fichiers personnels (pas dans Windows, "
                  "les logiciels ni les jeux, où des copies sont normales). La comparaison lit le contenu des "
                  "fichiers sans rien modifier et peut prendre quelques minutes.")


class Travail(QThread):
    """Analyse longue (stockage, doublons, test de connexion, mise à jour) hors du thread de l'interface ; arrêtable.

    `discret` : en priorité basse, pour ne pas ralentir ce que l'utilisateur fait à côté (sauf une mesure du réseau,
    qu'un thread freiné fausserait).
    """

    avance = Signal(object)  # valeurs de la progression, telles que la fonction les donne
    termine = Signal(object)  # résultat, None si l'analyse a été arrêtée, ou {"erreur": texte}

    def __init__(self, fonction: Callable[[Callable, Callable[[], bool]], dict | None], erreur: str,
                 discret: bool = True) -> None:
        super().__init__()
        self.fonction, self.erreur, self.discret = fonction, erreur, discret
        self.arret = threading.Event()

    def run(self) -> None:
        try:
            with arriere_plan() if self.discret else nullcontext():
                resultat = self.fonction(lambda *valeurs: self.avance.emit(valeurs), self.arret.is_set)
        except Exception:  # n'importe quelle panne : la page l'annonce au lieu de rester bloquée
            journal.exception(self.erreur)
            resultat = {"erreur": f"{self.erreur} {AIDE}"}
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


def parts_du_disque(resultat: dict) -> list[tuple[str, str, int]]:
    """(nom, teinte, taille) de chaque groupe de catégories qui occupe de la place, dans l'ordre de la barre."""
    tailles = {c["cle"]: c["taille"] for c in resultat["categories"]}
    groupes = [(nom, teinte, sum(tailles.get(cle, 0) for cle in cles)) for nom, teinte, cles in GROUPES]
    return [groupe for groupe in groupes if groupe[2] > 0]


class TexteCoupe(QLabel):
    """Texte sur une ligne, coupé au milieu s'il est trop long (« C:\\Users\\…\\film.mkv »), complet au survol
    seulement s'il est coupé (sinon, l'infobulle répéterait ce qui est déjà écrit)."""

    def __init__(self, texte: str, **proprietes) -> None:
        super().__init__(texte, **proprietes)
        self.setMinimumWidth(60)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._coupe = (-1, "")  # (largeur, texte coupé) : recalculé seulement quand la largeur change

    def paintEvent(self, _evenement) -> None:
        if self._coupe[0] != self.width():
            self._coupe = (self.width(), self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideMiddle,
                                                                       self.width()))
            self.setToolTip(self.text() if self._coupe[1] != self.text() else "")
        coupe = self._coupe[1]
        # Dessiné par le style : la couleur de la feuille de style (objectName) est respectée.
        alignement = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        self.style().drawItemText(QPainter(self), self.rect(), alignement, self.palette(), self.isEnabled(), coupe,
                                  self.foregroundRole())


def colonne_chiffres(haut: str, bas: str) -> QWidget:
    """Taille en gras et précision discrète dessous, sur une largeur fixe : les barres restent comparables."""
    grand = QLabel(haut, font=theme.police("chiffres"),
                   alignment=Qt.AlignmentFlag.AlignRight)
    petit = QLabel(bas, objectName="discret", font=theme.police("legende"), alignment=Qt.AlignmentFlag.AlignRight)
    colonne = QWidget(fixedWidth=LARGEUR_CHIFFRES)
    chiffres = QVBoxLayout(colonne)
    chiffres.setContentsMargins(0, 0, 0, 0)
    chiffres.setSpacing(2)
    chiffres.addWidget(grand)
    chiffres.addWidget(petit)
    chiffres.addStretch()
    return colonne


Action = Callable[[str, bool], None]  # (chemin, dossier ?)


class LigneElement(QFrame):
    """Un dossier ou un fichier : nom, emplacement, taille, « Afficher » pour le voir dans l'Explorateur,
    et « Supprimer » si `supprimer` est donné (tout, sauf ce qui casserait Windows ou le profil)."""

    def __init__(self, element: dict, montrer: Action, categorie: str | None = None,
                 supprimer: Action | None = None) -> None:
        super().__init__(objectName="ligne")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        icone = QLabel()
        icone.setPixmap(theme.pixmap_icone("dossier" if element["dossier"] else "fichier", theme.TEXTE_3, 16))
        textes = QVBoxLayout()
        textes.setSpacing(1)
        textes.addWidget(TexteCoupe(element["nom"], font=theme.police("fort")))
        if element["chemin"]:
            textes.addWidget(TexteCoupe(element["chemin"], objectName="discret", font=theme.police("legende")))
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(12, 8, 8, 8)
        disposition.setSpacing(12)
        disposition.addWidget(icone)
        disposition.addLayout(textes, 1)
        if categorie:  # même couleur que sa part dans la barre du disque
            disposition.addWidget(etiquette_couleur(stockage.NOMS[categorie],
                                                    theme.TEINTES[TEINTE_CATEGORIE[categorie]]))
        taille = QLabel(taille_lisible(element["taille"]), font=theme.police("chiffres"),
                        alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        taille.setMinimumWidth(70)
        disposition.addWidget(taille)
        if element["chemin"]:
            afficher = bouton("Afficher", "lien", "ouvrir", theme.ACCENT_CLAIR, 12)
            afficher.clicked.connect(lambda: montrer(element["chemin"], element["dossier"]))
            disposition.addWidget(afficher)
        if supprimer:
            effacer = bouton("Supprimer", "supprimer", "corbeille", theme.TEXTE_2, 12,
                             accessibleName=f"Supprimer {os.path.basename(element['chemin'])}")
            effacer.clicked.connect(lambda: supprimer(element["chemin"], element["dossier"]))
            disposition.addWidget(effacer)


def si_supprimable(supprimer: Action, chemin: str | None) -> Action | None:
    """L'action « Supprimer », sauf pour ce qui casserait Windows ou le profil (voir stockage.supprimable)."""
    return supprimer if stockage.supprimable(chemin) else None


class LigneDepliable(QFrame):
    """Ligne dont l'en-tête, cliqué (ou Entrée, Espace au clavier), déplie un détail en douceur."""

    def __init__(self, entete: QHBoxLayout, detail: QWidget, nom: str) -> None:
        super().__init__(objectName="ligne")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)  # cadre de focus au clavier seulement, pas après un clic
        self.setAccessibleName(nom)
        self.ouvert = False
        self.chevron = QLabel()
        self.chevron.setPixmap(theme.pixmap_icone("deplier", theme.TEXTE_3, 12))
        entete.addWidget(self.chevron, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.detail = detail
        self.detail.setMaximumHeight(0)
        self.detail.setCursor(Qt.CursorShape.ArrowCursor)
        # Dépliage en douceur (hauteur animée), comme le détail des cartes du bilan.
        self.animation = QVariantAnimation(self, duration=240, easingCurve=QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(lambda hauteur: self.detail.setMaximumHeight(round(hauteur)))
        self.animation.finished.connect(self._fin_animation)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(12, 12, 14, 12)
        disposition.setSpacing(0)
        disposition.addLayout(entete)
        disposition.addWidget(self.detail)

    def preparer_detail(self) -> None:
        """Remplit le détail au premier dépliage (ici, rien à faire : il est rempli dès la création)."""

    def basculer(self) -> None:
        self.ouvert = not self.ouvert
        if self.ouvert:
            self.preparer_detail()
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

    def deplier(self) -> None:
        """Ouvre tout de suite, sans animation : la ligne remplace une ligne qui était ouverte."""
        self.preparer_detail()
        self.ouvert = True
        self.chevron.setPixmap(theme.pixmap_icone("replier", theme.TEXTE_3, 12))
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


def detail_vide(marge_gauche: int) -> tuple[QWidget, QVBoxLayout]:
    detail = QWidget()
    contenu = QVBoxLayout(detail)
    contenu.setContentsMargins(marge_gauche, 10, 0, 2)
    contenu.setSpacing(2)
    return detail, contenu


class LigneCategorie(LigneDepliable):
    """Une catégorie : tuile, nom, explication, taille et part du disque ; un clic déplie ce qu'elle contient.

    Ce qu'elle contient n'est créé qu'au premier dépliage : une centaine de lignes en moins à fabriquer à
    l'arrivée des résultats, et à remettre en page à chaque dépliage ou redimensionnement.
    `occupe` : vrai pendant une analyse, où les boutons « Supprimer » créés naissent désactivés.
    """

    def __init__(self, categorie: dict, utilise: int, montrer: Action, ouvrir: Callable[[str], None],
                 supprimer: Action, occupe: Callable[[], bool] = lambda: False) -> None:
        barre = BarreScore(5)
        textes = QVBoxLayout()
        textes.setSpacing(3)
        textes.addWidget(QLabel(categorie["nom"], font=theme.police("fort")))
        textes.addWidget(QLabel(categorie["description"], objectName="secondaire", wordWrap=True,
                                font=theme.police("legende")))
        textes.addSpacing(5)
        textes.addWidget(barre)
        entete = QHBoxLayout()
        entete.setSpacing(14)
        entete.addWidget(TuileIcone(categorie["cle"], TEINTE_CATEGORIE[categorie["cle"]], 34),
                         alignment=Qt.AlignmentFlag.AlignTop)
        entete.addLayout(textes, 1)
        entete.addWidget(colonne_chiffres(taille_lisible(categorie["taille"]),
                                          part_lisible(categorie["taille"], utilise)))

        detail, self.contenu = detail_vide(42)
        super().__init__(entete, detail, f"{categorie['nom']} : {taille_lisible(categorie['taille'])}")
        self.categorie, self.barre = categorie, barre
        self.a_preparer: tuple | None = (montrer, ouvrir, supprimer, occupe)

    def preparer_detail(self) -> None:
        if self.a_preparer is None:
            return
        (montrer, ouvrir, supprimer, occupe), self.a_preparer = self.a_preparer, None
        categorie, contenu = self.categorie, self.contenu
        for element in categorie["elements"][:NB_PAR_CATEGORIE]:
            ligne = LigneElement(element, montrer, supprimer=si_supprimable(supprimer, element["chemin"]))
            for effacer in ligne.findChildren(QPushButton, "supprimer"):
                effacer.setEnabled(not occupe())
            contenu.addWidget(ligne)
        if not categorie["elements"]:
            contenu.addWidget(QLabel("Rien à montrer ici.", objectName="secondaire"))
        if categorie["surtout_dans"]:
            lieux = ", ".join(f"{d['nom']} ({taille_lisible(d['taille'])})" for d in categorie["surtout_dans"])
            surtout = QLabel(f"Surtout dans : {lieux}", objectName="secondaire", wordWrap=True)
            surtout.setContentsMargins(12, 6, 0, 0)
            contenu.addWidget(surtout)
        if categorie["lien"]:
            libelle, cible = categorie["lien"]
            lien = bouton(libelle, "lien", "ouvrir", theme.ACCENT_CLAIR, 12)
            lien.clicked.connect(lambda: ouvrir(cible))
            contenu.addWidget(lien, alignment=Qt.AlignmentFlag.AlignLeft)

    def remplir(self, ratio: float, animer: bool) -> None:
        self.barre.definir(ratio, theme.TEINTES[TEINTE_CATEGORIE[self.categorie["cle"]]], animer)


class LigneDoublon(LigneDepliable):
    """Un groupe de doublons : ce qui est en double, combien de fois, la place en trop ; un clic montre où."""

    def __init__(self, groupe: dict, montrer: Action, supprimer: Action) -> None:
        icone = QLabel()
        icone.setPixmap(theme.pixmap_icone("dossier" if groupe["dossier"] else "fichier", theme.TEXTE_3, 16))
        nature = "dossiers identiques" if groupe["dossier"] else "exemplaires"
        textes = QVBoxLayout()
        textes.setSpacing(2)
        textes.addWidget(TexteCoupe(groupe["nom"], font=theme.police("fort")))
        textes.addWidget(QLabel(f"{len(groupe['copies'])} {nature} de {taille_lisible(groupe['taille'])}",
                                objectName="secondaire", font=theme.police("legende")))
        entete = QHBoxLayout()
        entete.setSpacing(12)
        entete.addWidget(icone, alignment=Qt.AlignmentFlag.AlignTop)
        entete.addLayout(textes, 1)
        entete.addWidget(colonne_chiffres(taille_lisible(groupe["en_trop"]), "en trop"))

        detail, contenu = detail_vide(16)
        for copie in groupe["copies"]:
            ou = f"Dans {stockage.nom_element(os.path.dirname(copie))}"
            contenu.addWidget(LigneElement({"nom": ou, "chemin": copie, "taille": groupe["taille"],
                                            "dossier": groupe["dossier"]}, montrer,
                                           supprimer=si_supprimable(supprimer, copie)))
        super().__init__(entete, detail, f"{groupe['nom']} : {len(groupe['copies'])} {nature}")
        self.groupe = groupe


def carte_liste(marges: tuple[int, int, int, int] = (8, 8, 8, 8)) -> tuple[Verre, QVBoxLayout]:
    """Carte de verre dont les lignes sont séparées par un trait fin."""
    cadre = Verre()
    disposition = QVBoxLayout(cadre)
    disposition.setContentsMargins(*marges)
    disposition.setSpacing(2)
    cadre.separateurs = disposition
    return cadre, disposition


def vider(disposition: QVBoxLayout) -> None:
    while disposition.count():
        ancien = disposition.takeAt(0).widget()
        ancien.hide()  # caché tout de suite : la suppression n'a lieu qu'au prochain tour de Qt
        ancien.deleteLater()


def lignes(disposition: QVBoxLayout) -> list[QWidget]:
    return [disposition.itemAt(i).widget() for i in range(disposition.count())]


def titre(texte: str) -> QLabel:
    etiquette = titre_section(texte)
    etiquette.setContentsMargins(4, 10, 0, 0)
    return etiquette


class PageStockage(Page):
    """Contenu de l'onglet Stockage. La fenêtre le place dans une zone de défilement."""

    statut = Signal(str, str)  # message à annoncer et sa nature (« info », « valide » ou « erreur »)
    occupee = Signal(bool)  # analyse en cours : la fenêtre bloque le changement de mode clair/sombre

    def __init__(self, ouvrir: Callable[[str], None], resultat: dict | None = None, racine: str | None = None,
                 doublons_trouves: dict | None = None) -> None:
        super().__init__()
        self.ouvrir = ouvrir
        self.resultat = resultat
        self.doublons = doublons_trouves
        # Le thread est gardé après sa fin : son signal de fin arrive un instant avant qu'il s'arrête,
        # et Qt plante s'il détruit un thread encore actif. `occupe` dit si une analyse est en cours.
        self.travail: Travail | None = None
        self.occupe = False
        self.espace_utilise = 0  # au lancement de l'analyse : sert à estimer sa progression
        self.disques = disque.lister_disques()
        self.racine = racine or (resultat["racine"] if resultat else stockage.disque_systeme())

        disposition = self.disposition
        disposition.addWidget(self._heros())
        self.sections = []  # titres et cartes montrés seulement après l'analyse
        for intitule, cadre in ((titre("Ce qui prend le plus de place"), self._plus_gros()),
                                (titre("En double"), self._doublons()),
                                (titre("Par catégorie"), self._categories())):
            disposition.addWidget(intitule)
            disposition.addWidget(cadre)
            self.sections += [intitule, cadre]
        disposition.addWidget(self._aide())
        disposition.addWidget(pied_de_page())
        disposition.addStretch()

        if resultat:
            self.afficher(resultat, animer=False)  # même analyse : rien ne se re-remplit
        else:
            self._sans_resultat(animer=False)

    # --- Construction ---

    def _heros(self) -> Verre:
        self.etat = pastille()
        actuel = next((numero for numero, d in enumerate(self.disques)
                       if os.path.normcase(d["disque"]) == os.path.normcase(self.racine)), 0)
        self.choix = Segmente([f"Disque {d['disque'].rstrip(os.sep)}" for d in self.disques] or ["Disque"], actuel)
        self.choix.setAccessibleName("Disque à analyser")
        self.choix.setVisible(len(self.disques) > 1)
        self.choix.choisi.connect(self.changer_disque)
        haut = QHBoxLayout()
        haut.addWidget(self.etat)
        haut.addStretch()
        haut.addWidget(self.choix)

        self.utilise = QLabel(font=theme.police("grand"))
        self.sur = QLabel(objectName="secondaire", font=theme.police("corps"))
        chiffres = QHBoxLayout()
        chiffres.setSpacing(12)
        chiffres.addWidget(self.utilise, alignment=Qt.AlignmentFlag.AlignBottom)
        chiffres.addWidget(self.sur, 1, alignment=Qt.AlignmentFlag.AlignBottom)
        self.jauge = BarreEmpilee()
        self.legende = Legende()
        self.info = QLabel(objectName="secondaire", wordWrap=True)

        self.bouton = bouton("", "principal", "analyser", "white", 15, font=theme.police("fort"))
        self.bouton.clicked.connect(self.lancer)
        self.progression, self.glissement = self._barre_progression()

        cadre = Verre(rayon=26)
        disposition = QVBoxLayout(cadre)
        disposition.setContentsMargins(28, 22, 28, 24)
        disposition.setSpacing(10)
        disposition.addLayout(haut)
        disposition.addSpacing(4)
        disposition.addLayout(chiffres)
        disposition.addSpacing(2)
        disposition.addWidget(self.jauge)
        disposition.addWidget(self.legende)
        disposition.addWidget(self.info)
        disposition.addSpacing(8)
        disposition.addWidget(self.bouton, alignment=Qt.AlignmentFlag.AlignLeft)
        disposition.addWidget(self.progression)
        return cadre

    @staticmethod
    def _barre_progression() -> tuple[QProgressBar, QPropertyAnimation]:
        """Barre graduée en millièmes, qui glisse d'une valeur à l'autre au lieu de sauter."""
        barre = QProgressBar(textVisible=False, maximum=1000)
        barre.hide()
        return barre, QPropertyAnimation(barre, b"value", barre, duration=450, easingCurve=QEasingCurve.Type.OutCubic)

    def _plus_gros(self) -> Verre:
        cadre, self.liste_plus_gros = carte_liste()
        return cadre

    def _categories(self) -> Verre:
        cadre, self.liste_categories = carte_liste()
        return cadre

    def _doublons(self) -> Verre:
        cadre = Verre()
        disposition = QVBoxLayout(cadre)
        disposition.setContentsMargins(22, 18, 22, 18)
        disposition.setSpacing(10)
        self.intro_doublons = QLabel(TEXTE_DOUBLONS, objectName="secondaire", wordWrap=True)
        self.resume_doublons = QLabel(wordWrap=True, font=theme.police("carte"))
        self.note_doublons = QLabel(objectName="secondaire", wordWrap=True)
        liste = QWidget()
        self.liste_doublons = QVBoxLayout(liste)
        self.liste_doublons.setContentsMargins(0, 0, 0, 0)
        self.liste_doublons.setSpacing(2)
        self.info_doublons = QLabel(objectName="secondaire", wordWrap=True)
        self.progression_doublons, self.glissement_doublons = self._barre_progression()
        self.bouton_doublons = bouton("", "", "copier", theme.TEXTE, 14)
        self.bouton_doublons.clicked.connect(self.chercher_doublons)
        for widget in (self.intro_doublons, self.resume_doublons, self.note_doublons, liste, self.info_doublons,
                       self.progression_doublons):
            disposition.addWidget(widget)
        disposition.addWidget(self.bouton_doublons, alignment=Qt.AlignmentFlag.AlignLeft)
        return cadre

    def _aide(self) -> Verre:
        cadre = Verre(ombre=False)
        disposition = QVBoxLayout(cadre)
        disposition.setContentsMargins(22, 16, 22, 14)
        disposition.setSpacing(6)
        texte = QLabel("Pour faire de la place sans risque, commence par les fichiers temporaires et la Corbeille, "
                       "puis trie Téléchargements. Pour enlever un jeu ou un logiciel, désinstalle-le depuis les "
                       "Paramètres ou son lanceur (Steam, Epic…) : supprimer son dossier à la main laisse des "
                       "restes. Ici, « Supprimer » efface un dossier ou un fichier définitivement, sans passer par "
                       "la Corbeille : vérifie avec « Afficher » avant. Windows et ton profil restent protégés.",
                       objectName="secondaire", wordWrap=True)
        libelle, cible = stockage.LIEN_STOCKAGE
        lien = bouton(libelle, "lien", "ouvrir", theme.ACCENT_CLAIR, 12)
        lien.clicked.connect(lambda: self.ouvrir(cible))
        disposition.addWidget(texte)
        disposition.addWidget(lien, alignment=Qt.AlignmentFlag.AlignLeft)
        return cadre

    # --- Affichage ---

    def _remplissage(self, utilise: int, total: int, libre: int, animer: bool,
                     parts: list[tuple[str, str, int]] | None = None) -> None:
        """En-tête : espace utilisé du disque, avec un mot et une couleur selon son remplissage.

        `parts` (après l'analyse) : la barre est découpée par groupe de catégories, avec sa légende.
        """
        pourcentage = 100 * utilise / total if total else 0
        niveau = niveau_remplissage(pourcentage)
        self.etat.setText(ETATS[niveau])
        self.etat.setProperty("niveau", niveau)
        repolir(self.etat)
        self.utilise.setText(f"{taille_lisible(utilise)} utilisés")
        self.sur.setText(f"sur {taille_lisible(total)} · {taille_lisible(libre)} libres · {pourcentage:.0f} % utilisés")
        if parts:
            self.jauge.definir([(taille / total, theme.TEINTES[teinte]) for _nom, teinte, taille in parts], animer)
            self.legende.definir([(theme.TEINTES[teinte], nom, taille_lisible(taille)) for nom, teinte, taille in parts]
                                 + [(theme.REMPLI, "Libre", taille_lisible(libre))])
        else:
            self.jauge.definir([(utilise / total if total else 0, theme.VIFS[niveau])], animer)
        self.legende.setVisible(bool(parts))

    @staticmethod
    def _message(etiquette: QLabel, texte: str, erreur: bool = False) -> None:
        etiquette.setText(texte)
        etiquette.setObjectName("erreur" if erreur else "secondaire")
        repolir(etiquette)

    def _sans_resultat(self, erreur: str | None = None, animer: bool = True) -> None:
        """Avant toute analyse de ce disque : son remplissage, lu tout de suite, et l'invitation à analyser."""
        self.resultat = self.doublons = None
        try:
            usage = psutil.disk_usage(self.racine)
            self._remplissage(usage.used, usage.total, usage.free, animer)
        except OSError:
            journal.exception("Disque %s illisible", self.racine)
        self._message(self.info, erreur or "Lance l'analyse pour voir ce qui prend de la place. Elle lit les "
                                           "dossiers sans rien changer et peut prendre une ou deux minutes.",
                      erreur=bool(erreur))
        self.bouton.setText("  Analyser le stockage")
        for widget in self.sections:
            widget.hide()

    def afficher(self, resultat: dict, animer: bool = True) -> None:
        self.resultat = resultat
        utilise = resultat["utilise"]
        self._remplissage(utilise, resultat["total"], resultat["libre"], animer, parts_du_disque(resultat))
        self._message(self.info, f"Analyse du {resultat['date']:%d/%m/%Y à %H:%M} : "
                                 f"{nombre_lisible(resultat['fichiers'])} fichiers parcourus en "
                                 f"{resultat['duree']:.0f} s.")
        self.bouton.setText("  Relancer l'analyse")
        for widget in self.sections:
            widget.show()

        # Ce qui prend le plus de place, toutes catégories confondues (sauf Système : rien à y faire).
        elements = sorted(((e, c["cle"]) for c in resultat["categories"] if c["cle"] != "systeme"
                           for e in c["elements"]), key=lambda paire: paire[0]["taille"], reverse=True)
        vider(self.liste_plus_gros)
        for position, (element, cle) in enumerate(elements[:NB_PLUS_GROS]):
            ligne = LigneElement(element, self.montrer, cle, si_supprimable(self.supprimer, element["chemin"]))
            self.liste_plus_gros.addWidget(ligne)
            if animer:
                apparaitre(ligne, delai=position * 40)
        for widget in self.sections[:2]:
            widget.setVisible(bool(elements))

        vider(self.liste_categories)
        for categorie in sorted(resultat["categories"], key=lambda c: c["taille"], reverse=True):
            ligne = LigneCategorie(categorie, utilise, self.montrer, self.ouvrir, self.supprimer, self.en_cours)
            self.liste_categories.addWidget(ligne)
            ligne.remplir(categorie["taille"] / utilise if utilise else 0, animer)
        self._afficher_doublons(animer)

    def _afficher_doublons(self, animer: bool) -> None:
        """Section « En double » : l'invitation à chercher, ou ce qui a été trouvé."""
        vider(self.liste_doublons)
        self.intro_doublons.setVisible(self.doublons is None)
        self.resume_doublons.setVisible(self.doublons is not None)
        self.note_doublons.setVisible(bool(self.doublons and self.doublons["nombre"]))
        self.info_doublons.hide()
        self.bouton_doublons.setText(" Chercher les doublons" if self.doublons is None else " Relancer la recherche")
        if self.doublons is None:
            return
        nombre, groupes = self.doublons["nombre"], self.doublons["groupes"]
        if not nombre:
            self.resume_doublons.setText("Aucun doublon d'au moins 1 Mo dans tes fichiers personnels.")
            return
        self.resume_doublons.setText(f"{nombre} {'groupe' if nombre == 1 else 'groupes'} en double : jusqu'à "
                                     f"{taille_lisible(self.doublons['en_trop'])} à récupérer")
        montres = f" Les {len(groupes)} qui prennent le plus de place sont montrés." if nombre > len(groupes) else ""
        self.note_doublons.setText("En gardant un seul exemplaire de chacun. Clique sur un groupe pour voir où sont "
                                   "les copies : « Supprimer » en efface une définitivement, après confirmation."
                                   f"{montres}")
        for position, groupe in enumerate(groupes):
            ligne = LigneDoublon(groupe, self.montrer, self.supprimer)
            self.liste_doublons.addWidget(ligne)
            if animer:
                apparaitre(ligne, delai=min(position, 10) * 40)

    def lignes_categories(self) -> list[LigneCategorie]:
        return lignes(self.liste_categories)

    def lignes_doublons(self) -> list[LigneDoublon]:
        return lignes(self.liste_doublons)

    # --- Analyses (une seule à la fois) ---

    def en_cours(self) -> bool:
        return self.occupe

    def _occuper(self, occupe: bool) -> None:
        """Pendant une analyse, une recherche ou une suppression, rien d'autre ne se lance."""
        self.occupe = occupe
        for widget in (self.bouton, self.bouton_doublons, self.choix, *self.findChildren(QPushButton, "supprimer")):
            widget.setEnabled(not occupe)
        self.occupee.emit(occupe)

    def _demarrer(self, fonction: Callable, erreur: str, avancer: Callable, finir: Callable) -> None:
        self.arreter()  # la précédente finit tout juste : on attend son thread avant de le remplacer
        self._occuper(True)
        self.travail = Travail(fonction, erreur)
        self.travail.avance.connect(avancer)
        self.travail.termine.connect(finir)
        self.travail.start()

    def _terminer(self) -> None:
        self._occuper(False)

    def _arreter_en_cours(self, bouton_en_cours: QPushButton) -> None:
        """Le bouton de l'analyse en cours sert à l'arrêter."""
        self.travail.arret.set()
        bouton_en_cours.setEnabled(False)
        texte = bouton_en_cours.text()
        bouton_en_cours.setText(" " * (len(texte) - len(texte.lstrip())) + "Arrêt en cours…")

    @staticmethod
    def _glisser(animation: QPropertyAnimation, valeur: int) -> None:
        animation.stop()
        animation.setEndValue(valeur)  # depuis la position du moment
        animation.start()

    def lancer(self) -> None:
        """Lance l'analyse du disque choisi ; pendant l'analyse, le même bouton l'arrête."""
        if self.en_cours():
            self._arreter_en_cours(self.bouton)
            return
        try:
            self.espace_utilise = psutil.disk_usage(self.racine).used
        except OSError:
            self.espace_utilise = 0  # progression inconnue : la barre reste au début, le texte avance
        racine = self.racine
        self._demarrer(lambda progression, arret: stockage.scan(racine, progression, arret),
                       "L'analyse du stockage n'a pas pu aboutir.", self.avancer, self.fin)
        self.bouton.setEnabled(True)  # il sert à arrêter
        self.bouton.setText("  Arrêter l'analyse")
        self.glissement.stop()
        self.progression.setValue(0)
        self.progression.show()
        self._message(self.info, "Analyse en cours : lecture des dossiers, sans rien modifier…")

    def avancer(self, valeurs: tuple[int, int]) -> None:
        """Progression estimée : la part de l'espace utilisé déjà comptée (Système, lui, n'est pas parcouru)."""
        octets, nombre = valeurs
        self._glisser(self.glissement, min(990, round(1000 * octets / self.espace_utilise))
                      if self.espace_utilise else 0)
        self.info.setText(f"Analyse en cours : {nombre_lisible(nombre)} fichiers parcourus, "
                          f"{taille_lisible(octets)} comptés…")

    def fin(self, resultat: dict | None) -> None:
        self._terminer()
        self.progression.hide()
        if resultat is None:  # arrêtée : on garde ce qui était affiché
            self.statut.emit("Analyse du stockage arrêtée.", "info")
            if self.resultat:
                self.afficher(self.resultat, animer=False)
            else:
                self._sans_resultat()
            return
        if "erreur" in resultat:
            self.statut.emit("L'analyse du stockage n'a pas pu aboutir.", "erreur")
            self._sans_resultat(resultat["erreur"])
            return
        resultat["date"] = datetime.now()
        self.doublons = None  # les fichiers ont pu changer depuis la dernière recherche
        self.afficher(resultat)

    def chercher_doublons(self) -> None:
        """Lance la recherche des doublons parmi les fichiers relevés ; pendant la recherche, le bouton l'arrête."""
        if self.en_cours():
            self._arreter_en_cours(self.bouton_doublons)
            return
        personnels = self.resultat["personnels"]
        self._demarrer(lambda progression, arret: doublons.chercher(personnels, progression, arret),
                       "La recherche des doublons n'a pas pu aboutir.", self.avancer_doublons, self.fin_doublons)
        self.bouton_doublons.setEnabled(True)  # il sert à arrêter
        self.bouton_doublons.setText(" Arrêter la recherche")
        self.glissement_doublons.stop()
        self.progression_doublons.setValue(0)
        self.progression_doublons.show()
        self._message(self.info_doublons, "Recherche en cours : comparaison des fichiers, sans rien modifier…")
        self.info_doublons.show()

    def avancer_doublons(self, valeurs: tuple[str, int, int]) -> None:
        """Comparaison rapide (le premier dixième de la barre), puis lecture du contenu (le reste)."""
        etape, fait, total = valeurs
        if etape == "rapide":
            valeur = round(100 * fait / total) if total else 100
            texte = f"Comparaison rapide : {nombre_lisible(fait)} fichiers sur {nombre_lisible(total)}…"
        else:
            valeur = 100 + (round(900 * fait / total) if total else 900)
            texte = f"Lecture du contenu : {taille_lisible(fait)} sur {taille_lisible(total)}…"
        self._glisser(self.glissement_doublons, valeur)
        self.info_doublons.setText(texte)

    def fin_doublons(self, resultat: dict | None) -> None:
        self._terminer()
        self.progression_doublons.hide()
        if resultat is None:
            self.statut.emit("Recherche des doublons arrêtée.", "info")
            self._afficher_doublons(animer=False)
            return
        if "erreur" in resultat:
            self.statut.emit("La recherche des doublons n'a pas pu aboutir.", "erreur")
            self._afficher_doublons(animer=False)
            self._message(self.info_doublons, resultat["erreur"], erreur=True)
            self.info_doublons.show()
            return
        self.doublons = resultat
        self._afficher_doublons(animer=True)

    def arreter(self) -> None:
        """Arrête l'analyse et attend la fin de son thread, avant que la page ou le thread soient détruits."""
        if self.travail:
            self.travail.arret.set()
            self.travail.wait()

    def changer_disque(self, numero: int) -> None:
        self.racine = self.disques[numero]["disque"]
        self._sans_resultat()

    # --- Actions ---

    def montrer(self, chemin: str, dossier: bool) -> None:
        """Ouvre l'emplacement dans l'Explorateur : le dossier lui-même, ou celui du fichier, fichier sélectionné."""
        try:
            if dossier:
                os.startfile(chemin)  # comme un double-clic
            else:
                subprocess.Popen(["explorer", "/select,", chemin])
        except OSError:
            journal.exception("Impossible d'afficher %s", chemin)
            self.statut.emit("Cet emplacement n'a pas pu s'ouvrir.", "erreur")

    def supprimer(self, chemin: str, dossier: bool) -> None:
        """« Supprimer » : supprime définitivement un fichier ou un dossier de l'analyse, après confirmation,
        puis met les chiffres à jour. Seule action de la page qui modifie le PC, et seulement sur ce clic."""
        nom = os.path.basename(chemin)
        if self.en_cours():
            return
        categorie = self._categorie(chemin)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)  # un gros dossier se mesure en quelques secondes
        try:
            avant, nombre = stockage.contenu(chemin, categorie)
        except OSError:
            self.statut.emit(f"« {nom} » est introuvable : il a peut-être déjà été déplacé ou supprimé.", "erreur")
            return
        finally:
            QApplication.restoreOverrideCursor()
        if not self.confirmer_suppression(chemin, dossier, sum(avant.values()), nombre, categorie):
            return
        focus = QApplication.focusWidget()
        if focus and self.isAncestorOf(focus):
            focus.clearFocus()  # sinon Qt donne le focus à la ligne suivante et fait défiler la page
        self._occuper(True)  # Windows peut montrer sa progression : rien d'autre ne se lance pendant ce temps
        try:
            fichiers.supprimer(chemin, int(self.window().winId()))
            apres = stockage.contenu(chemin, categorie)[0] if os.path.lexists(chemin) else {}
        except (OSError, ValueError):
            journal.exception("Impossible de supprimer %s", chemin)
            self.statut.emit(f"« {nom} » n'a pas pu être supprimé.", "erreur")
            return
        finally:
            self._occuper(False)
        enleve = {cle: octets - apres.get(cle, 0) for cle, octets in avant.items() if octets > apres.get(cle, 0)}
        reste = os.path.lexists(chemin)
        if reste and not enleve:  # fichier ouvert dans un programme, accès refusé… (Windows l'a dit)
            self.statut.emit(f"« {nom} » n'a pas été supprimé : il est peut-être ouvert dans un programme.", "erreur")
            return
        try:
            stockage.retirer(self.resultat, chemin, dossier, enleve)
            if self.doublons:
                doublons.retirer(self.doublons, chemin)
        except OSError:
            journal.exception("Chiffres non mis à jour après la suppression de %s", chemin)
        self._rafraichir()
        libere = taille_lisible(sum(enleve.values()))
        if reste:
            self.statut.emit(f"« {nom} » n'a été supprimé qu'en partie ({libere} libérés) : un fichier est "
                             "peut-être ouvert dans un programme.", "erreur")
        else:
            self.statut.emit(f"« {nom} » supprimé : {libere} libérés.", "valide")

    def _categorie(self, chemin: str) -> str | None:
        """Catégorie où l'analyse a rangé cet élément ; None pour une copie en double (fichiers personnels)."""
        return next((c["cle"] for c in self.resultat["categories"] for e in c["elements"] if e["chemin"] == chemin),
                    None)

    def confirmer_suppression(self, chemin: str, dossier: bool, taille: int, nombre: int,
                              categorie: str | None = None) -> bool:
        """Demande confirmation avant de supprimer définitivement ; vrai si c'est confirmé."""
        nom = os.path.basename(chemin)
        if dossier:
            quoi = (f"Le dossier et tout son contenu ({nombre_lisible(nombre)} "
                    f"{'fichier' if nombre <= 1 else 'fichiers'}, {taille_lisible(taille)})")
        else:
            quoi = f"Le fichier ({taille_lisible(taille)})"
        conseil = ("\n\nSi c'est un jeu ou un logiciel installé, mieux vaut le désinstaller (Paramètres ou son "
                   "lanceur) : supprimer son dossier laisse des restes." if categorie in ("jeux", "applications")
                   else "")
        feuille = Feuille(self, f"Supprimer « {nom} » ?",
                          f"{quoi} sera supprimé définitivement, sans passer par la Corbeille : impossible de le "
                          "récupérer ensuite.",
                          f"Emplacement : {os.path.dirname(chemin)}{conseil}",
                          confirmer="Supprimer définitivement", destructif=True, icone="corbeille")
        return feuille.exec() == QDialog.DialogCode.Accepted

    def _rafraichir(self) -> None:
        """Après une suppression : les listes avec les chiffres à jour, dépliées comme avant."""
        categories = {ligne.categorie["cle"] for ligne in self.lignes_categories() if ligne.ouvert}
        groupes = [ligne.groupe for ligne in self.lignes_doublons() if ligne.ouvert]
        self.afficher(self.resultat, animer=False)
        for ligne in self.lignes_categories():
            if ligne.categorie["cle"] in categories:
                ligne.deplier()
        for ligne in self.lignes_doublons():
            if any(ligne.groupe is groupe for groupe in groupes):  # même groupe, mis à jour
                ligne.deplier()
