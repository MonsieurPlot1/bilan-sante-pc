"""Fenêtre principale de Bilan santé PC (PySide6)."""

import ctypes
import html
import importlib
import logging
import os
import sys
from ctypes import wintypes
from functools import cache

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QStandardPaths, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPalette
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QMainWindow, QProgressBar, QStackedWidget, QVBoxLayout, QWidget)

import config
import historique
from modules import fichiers, installation_pilotes, mise_a_jour, pilotes, score
from modules.disque import taille_lisible
from ui import analyse, theme
from ui.connexion import PageConnexion
from ui.stockage import PageStockage, Travail
from ui.verre import Ambiance, Page, Verre
from ui.widgets import (Annonce, BarreHaut, Carte, CarteConseil, DefilementDoux, Feuille, Fondu, Graphique, Infobulle,
                        Jauge, Logo, Segmente, apparaitre, bouton, melange, pastille, pied_de_page, repolir,
                        titre_section)

journal = logging.getLogger(__name__)

DUREE_FONDU = 300  # millisecondes : passage en douceur entre le mode clair et le mode sombre
DUREE_ONGLET = 180  # millisecondes : passage en douceur d'un onglet à l'autre
DELAI_RECHERCHE = 3000  # millisecondes après l'ouverture : la recherche de mise à jour ne freine pas le démarrage
ONGLETS = ["Bilan de santé", "Stockage", "Connexion"]
ONGLET_STOCKAGE, ONGLET_CONNEXION = 1, 2
DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # boutons de la barre de titre sombres
DWMWA_BORDER_COLOR, DWMWA_CAPTION_COLOR, DWMWA_TEXT_COLOR = 34, 35, 36  # Windows 11 : liseré, barre de titre
WTA_NONCLIENT, WTNCA_NODRAWCAPTION, WTNCA_NODRAWICON = 1, 0x1, 0x2  # barre de titre sans titre ni icône


class Analyse(QThread):
    """Lance l'analyse hors du thread de l'interface pour que la fenêtre ne gèle pas."""

    etape = Signal(int, int, str)  # parties finies, total, nom d'une partie encore en cours
    termine = Signal(object)

    def run(self) -> None:
        try:
            resultat = analyse.analyser(self.etape.emit)
        except Exception:  # panne imprévue : la fenêtre ne doit pas rester bloquée sur « Analyse en cours »
            journal.exception("Échec de l'analyse")
            resultat = analyse.echec()
        try:  # l'historique est un plus : s'il échoue, l'analyse s'affiche quand même
            resultat["historique"] = historique.enregistrer(resultat)
            resultat["comparaison"] = historique.comparer(resultat["historique"], analyse.NOMS)
        except Exception:
            journal.exception("Échec de l'historique")
            resultat["historique"] = None
        self.termine.emit(resultat)


def entete_section(titre: str, *droite: QWidget) -> QHBoxLayout:
    """Titre d'une section, avec ses éventuels boutons à droite."""
    ligne = QHBoxLayout()
    ligne.setContentsMargins(4, 10, 0, 0)
    ligne.addWidget(titre_section(titre))
    ligne.addStretch()
    for widget in droite:
        ligne.addWidget(widget)
    return ligne


class Fenetre(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Bilan santé PC")
        self.setMinimumSize(780, 580)
        ecran = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(min(1060, round(ecran.width() * 0.9)), min(800, round(ecran.height() * 0.9)))
        self.resultat: dict | None = None
        self.analyse: Analyse | None = None
        self.bilan_en_cours = False
        self.onglet = 0  # onglet affiché, gardé quand le contenu est recréé
        # Page Stockage : gardés ici, car la page est recréée au changement de mode clair/sombre.
        self.resultat_stockage: dict | None = None
        self.racine_stockage: str | None = None
        self.doublons_stockage: dict | None = None
        self.resultat_connexion: dict | None = None  # page Connexion : dernier test, pour la même raison
        self.nouvelle_version: dict | None = None  # version publiée plus récente (voir mise_a_jour.plus_recente)
        self.recherche: Travail | None = None
        self.telechargement: Travail | None = None
        # Mise à jour des pilotes en cours : ce qui s'installe, le téléchargement du pilote NVIDIA, puis l'installation
        # en administrateur, suivie toutes les demi-secondes.
        self.pilotes_a_installer: dict | None = None
        self.travail_pilotes: Travail | None = None
        self.processus_pilotes: int | None = None
        self.suivi_pilotes = QTimer(self, interval=500)
        self.suivi_pilotes.timeout.connect(self._suivre_pilotes)
        self.construire()
        colorer_barre_titre(self, *couleurs_cadre())  # barre de titre fondue dans la barre du haut
        epurer_barre_titre(self)

    def construire(self) -> None:
        """Crée le contenu de la fenêtre avec les couleurs du thème, et y remet les dernières analyses.

        En haut, la barre (application, onglets, mode) reste en place ; dessous, chaque onglet défile à part.
        Appelée aussi au changement de mode clair/sombre : l'ancien contenu est remplacé.
        """
        self.ambiance = Ambiance()
        self.pages = QStackedWidget()
        self.pages.addWidget(self._page_bilan())
        self.pages.addWidget(self._page_stockage())
        self.pages.addWidget(self._page_connexion())
        self.pages.setCurrentIndex(self.onglet)
        disposition = QVBoxLayout(self.ambiance)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(0)
        disposition.addWidget(self._barre())
        disposition.addWidget(self.pages, 1)
        self.annonce = Annonce(self.ambiance)
        self.setCentralWidget(self.ambiance)  # Qt supprime l'ancien contenu
        # Focus de départ sur le fond : le cadre de focus n'apparaît qu'en naviguant au clavier (Tab).
        self.ambiance.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.ambiance.setFocus()
        self._suivre_page()
        if self.resultat:
            self.afficher(self.resultat, animer=False)  # même analyse : l'anneau ne se re-remplit pas
        else:
            self.afficher_historique_existant()

    # --- Construction des zones de la fenêtre ---

    def _barre(self) -> BarreHaut:
        """Barre du haut : l'application à gauche, les onglets au milieu, à droite le mode clair/sombre et, quand une
        nouvelle version est publiée, le bouton « Mettre à jour »."""
        self.barre = barre = BarreHaut()
        gauche = QWidget()
        identite = QHBoxLayout(gauche)
        identite.setContentsMargins(0, 0, 0, 0)
        identite.setSpacing(10)
        identite.addWidget(Logo(28))
        identite.addWidget(QLabel("Bilan santé PC", font=theme.police("carte")))
        identite.addStretch()

        self.onglets = Segmente(ONGLETS, self.onglet)
        self.groupe_onglets = self.onglets.groupe
        self.onglets.choisi.connect(self.changer_page)

        texte, icone = ("Passer en mode sombre", "lune") if theme.CLAIR else ("Passer en mode clair", "soleil")
        self.mode = bouton("", "rond", icone, theme.TEXTE_2, 15, toolTip=texte, accessibleName=texte)
        self.mode.clicked.connect(self.changer_mode)
        self.bouton_maj = bouton(" Mettre à jour", "teinte", "telechargement", theme.ACCENT_CLAIR, 13)
        self.bouton_maj.clicked.connect(self.proposer_mise_a_jour)
        droite = QWidget()
        reglages = QHBoxLayout(droite)
        reglages.setContentsMargins(0, 0, 0, 0)
        reglages.setSpacing(8)
        reglages.addStretch()
        reglages.addWidget(self.bouton_maj)
        reglages.addWidget(self.mode)
        self._montrer_mise_a_jour()  # une fois rangé : montré sans parent, il s'ouvrirait en petite fenêtre

        # Côtés de même largeur (bouton de mise à jour compris, même caché) : les onglets restent pile au milieu.
        cote = max(gauche.sizeHint().width(),
                   self.bouton_maj.sizeHint().width() + reglages.spacing() + self.mode.sizeHint().width())
        for widget in (gauche, droite):
            widget.setFixedWidth(cote)
        grille = QGridLayout(barre)
        grille.setContentsMargins(22, 0, 18, 0)
        grille.addWidget(gauche, 0, 0, Qt.AlignmentFlag.AlignVCenter)
        grille.addWidget(self.onglets, 0, 1, Qt.AlignmentFlag.AlignCenter)
        grille.addWidget(droite, 0, 2, Qt.AlignmentFlag.AlignVCenter)
        grille.setColumnStretch(1, 1)
        return barre

    def _suivre_page(self) -> None:
        """La barre du haut et le fond suivent le défilement de l'onglet affiché."""
        zone = self.pages.currentWidget()
        self.barre.suivre(zone)
        self.ambiance.defilement = zone

    @staticmethod
    def _defilement(contenu: QWidget) -> DefilementDoux:
        defilement = DefilementDoux(widgetResizable=True, frameShape=QFrame.Shape.NoFrame,
                                    horizontalScrollBarPolicy=Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        defilement.setWidget(contenu)
        return defilement

    def _page_stockage(self) -> DefilementDoux:
        self.stockage = PageStockage(self.ouvrir, self.resultat_stockage, self.racine_stockage,
                                     self.doublons_stockage)
        self.stockage.statut.connect(lambda texte, nature: self.annonce.montrer(texte, nature))
        self.stockage.occupee.connect(self._autoriser_mode)
        return self._defilement(self.stockage)

    def _page_connexion(self) -> DefilementDoux:
        self.connexion = PageConnexion(self.ouvrir, self.resultat_connexion)
        self.connexion.statut.connect(lambda texte, nature: self.annonce.montrer(texte, nature))
        self.connexion.occupee.connect(self._autoriser_mode)
        return self._defilement(self.connexion)

    def _page_bilan(self) -> DefilementDoux:
        contenu = Page()
        disposition = contenu.disposition
        disposition.addWidget(self._heros())
        # Les conseils juste sous le score : ce qu'il y a à faire se voit sans faire défiler.
        disposition.addLayout(entete_section("Conseils"))
        disposition.addLayout(self._conseils())
        disposition.addLayout(self._historique())
        disposition.addLayout(entete_section("Détail par partie"))
        disposition.addLayout(self._cartes())
        disposition.addLayout(self._actions())
        disposition.addWidget(pied_de_page())
        disposition.addStretch()
        return self._defilement(contenu)

    def _heros(self) -> Verre:
        """Zone principale : l'anneau du score, son interprétation et le bouton d'analyse."""
        self.jauge = Jauge()
        self.etat = pastille("Pas encore analysé")
        self.phrase = QLabel("Clique sur « Analyser mon PC » pour commencer.", wordWrap=True,
                             font=theme.police("titre"))
        self.info = QLabel("L'analyse prend moins d'une minute. Elle lit ton PC sans rien changer.",
                           objectName="secondaire", wordWrap=True)
        self.bouton = bouton("  Analyser mon PC", "principal", "analyser", "white", 15,
                             font=theme.police("fort"))
        self.bouton.clicked.connect(self.lancer)
        # Graduée en centièmes de partie : la barre glisse d'une partie à l'autre au lieu de sauter.
        self.progression = QProgressBar(textVisible=False, maximum=len(analyse.MODULES) * 100)
        self.progression.hide()
        self.glissement = QPropertyAnimation(self.progression, b"value", self.progression,
                                             duration=450, easingCurve=QEasingCurve.Type.OutCubic)

        droite = QVBoxLayout()
        droite.setSpacing(8)
        droite.addStretch()
        droite.addWidget(self.etat, alignment=Qt.AlignmentFlag.AlignLeft)
        droite.addSpacing(2)
        droite.addWidget(self.phrase)
        droite.addWidget(self.info)
        droite.addSpacing(12)
        droite.addWidget(self.bouton, alignment=Qt.AlignmentFlag.AlignLeft)
        droite.addWidget(self.progression)
        droite.addStretch()

        cadre = Verre(rayon=26)
        ligne = QHBoxLayout(cadre)
        ligne.setContentsMargins(26, 24, 32, 24)
        ligne.setSpacing(30)
        ligne.addWidget(self.jauge)
        ligne.addLayout(droite, 1)
        return cadre

    def _historique(self) -> QVBoxLayout:
        effacer = bouton(" Effacer l'historique", "discret", "effacer", theme.TEXTE_2, 13)
        effacer.clicked.connect(self.effacer_historique)
        self.comparaison = QLabel(wordWrap=True, textFormat=Qt.TextFormat.RichText, minimumWidth=260)
        self.graphique = Graphique()
        cadre = Verre()
        corps = QHBoxLayout(cadre)
        corps.setContentsMargins(22, 18, 18, 14)
        corps.setSpacing(24)
        corps.addWidget(self.comparaison, 0, Qt.AlignmentFlag.AlignTop)
        corps.addWidget(self.graphique, 1)
        section = QVBoxLayout()
        section.setSpacing(16)
        section.addLayout(entete_section("Depuis la dernière fois", effacer))
        section.addWidget(cadre)
        return section

    def _cartes(self) -> QHBoxLayout:
        """Deux colonnes indépendantes : chaque carte garde la hauteur de son contenu."""
        self.cartes = {cle: Carte(cle, nom, analyse.COLONNES[cle]) for cle, nom, _ in analyse.MODULES}
        self.cartes["batterie"].hide()  # affichée seulement si une batterie est détectée
        # Boutons d'action des cartes : montrés seulement quand il y a quelque chose à faire (voir afficher).
        self.vider = bouton(" Vider la Corbeille", "", "effacer", theme.TEXTE, 13, enabled=False)
        self.vider.clicked.connect(self.vider_corbeille)
        self.vider.hide()
        self.cartes["fichiers"].layout().addWidget(self.vider, alignment=Qt.AlignmentFlag.AlignLeft)
        voir = bouton("Voir ce qui prend de la place", "lien", "stockage", theme.ACCENT_CLAIR, 12)
        voir.clicked.connect(lambda: self.changer_page(ONGLET_STOCKAGE))
        self.cartes["disque"].layout().addWidget(voir, alignment=Qt.AlignmentFlag.AlignLeft)
        self.bouton_pilotes = bouton(" Mettre à jour les pilotes", "", "telechargement", theme.TEXTE, 13, enabled=False)
        self.bouton_pilotes.clicked.connect(self.mettre_a_jour_pilotes)
        self.bouton_pilotes.hide()
        self.cartes["pilotes"].layout().addWidget(self.bouton_pilotes, alignment=Qt.AlignmentFlag.AlignLeft)
        colonnes = [QVBoxLayout(), QVBoxLayout()]
        for position, carte in enumerate(self.cartes.values()):
            colonnes[position % 2].addWidget(carte)
        ligne = QHBoxLayout()
        ligne.setSpacing(16)
        for colonne in colonnes:
            colonne.setSpacing(16)
            colonne.addStretch()
            ligne.addLayout(colonne, 1)
        return ligne

    def _conseils(self) -> QVBoxLayout:
        self.liste_conseils = QVBoxLayout()
        self.liste_conseils.setSpacing(10)
        self._remplacer_conseils([], "Les conseils s'afficheront après l'analyse.")
        return self.liste_conseils

    def _actions(self) -> QHBoxLayout:
        self.copier = bouton(" Copier le rapport", "", "copier", theme.TEXTE, 14, enabled=False)
        self.copier.clicked.connect(self.copier_rapport)
        self.enregistrer = bouton(" Enregistrer le rapport", "", "enregistrer", theme.TEXTE, 14, enabled=False)
        self.enregistrer.clicked.connect(self.enregistrer_rapport)
        ligne = QHBoxLayout()
        ligne.setContentsMargins(0, 4, 0, 0)
        ligne.setSpacing(10)
        ligne.addStretch()
        ligne.addWidget(self.copier)
        ligne.addWidget(self.enregistrer)
        return ligne

    # --- Affichage ---

    def _remplacer_conseils(self, conseils: list[str], message: str = "", liens: list | None = None,
                            animer: bool = False) -> None:
        """`animer` : les nouvelles cartes apparaissent en fondu, l'une après l'autre."""
        while self.liste_conseils.count():
            ancien = self.liste_conseils.takeAt(0).widget()
            ancien.hide()  # caché tout de suite : la suppression n'a lieu qu'au prochain tour de Qt
            ancien.deleteLater()
        for numero, (conseil, lien) in enumerate(zip(conseils, liens or [None] * len(conseils)), start=1):
            self.liste_conseils.addWidget(CarteConseil(numero, conseil, lien, self.ouvrir))
        if message:
            cadre = Verre(rayon=18)
            disposition = QVBoxLayout(cadre)
            disposition.setContentsMargins(20, 16, 20, 16)
            disposition.addWidget(QLabel(message, objectName="secondaire", wordWrap=True))
            self.liste_conseils.addWidget(cadre)
        if animer:
            for position in range(self.liste_conseils.count()):
                apparaitre(self.liste_conseils.itemAt(position).widget(), delai=position * 90)

    def _etat(self, texte: str, niveau: str) -> None:
        """Pastille au-dessus de la phrase du score : un mot, dans la couleur du niveau."""
        self.etat.setText(texte)
        self.etat.setProperty("niveau", niveau)
        repolir(self.etat)

    def _bouton_vider_pret(self, pleine: bool) -> None:
        """« Vider la Corbeille » : seulement quand elle contient quelque chose (un bouton grisé ne servirait à rien)."""
        self.vider.setVisible(pleine)
        self.vider.setEnabled(pleine)

    def _texte_comparaison(self, lignes: list[str]) -> None:
        """Une vraie comparaison : le score mis en avant, le reste plus discret. Un message seul : texte simple."""
        lignes = [html.escape(ligne) for ligne in lignes]
        if len(lignes) < 2:
            self.comparaison.setText(f"<span style='color:{theme.TEXTE_2}'>{''.join(lignes)}</span>")
            return
        tete, *reste = lignes
        # Une ligne par paragraphe, séparés d'un petit espace : une ligne trop longue qui passe à la ligne reste
        # serrée et ne passe pas pour la ligne suivante.
        detail = f"color:{theme.TEXTE_2}; margin-top:6px; margin-bottom:0"
        self.comparaison.setText(f"<div style='font-size:13.5pt; font-weight:700'>{tete}</div>"
                                 + "".join(f"<p style='{detail}'>{ligne}</p>" for ligne in reste))

    def lancer(self) -> None:
        self.bouton.setEnabled(False)
        self.bouton.setText("  Analyse en cours…")
        self._etat("Analyse en cours", "gris")
        self.phrase.setText("Analyse de ton PC en cours…")
        self.bilan_en_cours = True
        self._autoriser_mode()
        self.copier.setEnabled(False)
        self.enregistrer.setEnabled(False)
        self.vider.setEnabled(False)
        self.bouton_pilotes.setEnabled(False)
        self.glissement.stop()
        self.progression.setValue(0)
        self.progression.show()
        self.info.setText("La mesure des dossiers peut prendre une minute.")
        self.analyse = Analyse()
        self.analyse.etape.connect(self.avancer)
        self.analyse.termine.connect(self.afficher)
        self.analyse.start()

    def avancer(self, finies: int, total: int, nom: str) -> None:
        """Pendant l'analyse : les parties déjà finies, et l'une de celles encore en cours."""
        self.progression.setMaximum(total * 100)
        self.glissement.stop()
        self.glissement.setEndValue(finies * 100)  # depuis la position du moment
        self.glissement.start()
        self.info.setText(f"En cours : {nom} ({finies} parties sur {total} finies)…" if finies
                          else f"En cours : {nom}…")

    def afficher(self, resultat: dict, animer: bool = True) -> None:
        self.resultat = resultat
        note = analyse.score_global(resultat)
        niveau, phrase = analyse.interpretation(note)
        # La lueur prend la couleur de l'état du PC, une fois l'anneau rempli.
        self.ambiance.definir_teinte("neutre" if note is None else niveau, animer, self.jauge.animation.duration())
        self.jauge.definir(note, theme.VIFS[niveau], animer)
        self._etat(analyse.ETATS[niveau], niveau)
        self.phrase.setText(phrase)
        self.info.setText(f"Analyse du {resultat['date']:%d/%m/%Y à %H:%M}, terminée en {resultat['duree']:.0f} s.")

        bilan = resultat["bilan"]
        for cle, carte in self.cartes.items():
            carte.setVisible(cle in resultat["modules"])
            if cle not in resultat["modules"]:
                continue
            module = resultat["modules"][cle]
            ratio = bilan["scores"][cle] / bilan["bareme"][cle] if bilan and cle in bilan["scores"] else None
            carte.remplir(analyse.points_module(resultat, cle), ratio, module["constats"] if module else [],
                          analyse.lignes_detail(cle, module) if module else [], resultat["erreurs"].get(cle), animer)

        module_fichiers = resultat["modules"].get("fichiers")
        self._bouton_vider_pret(bool(module_fichiers and module_fichiers["corbeille"]))
        self._bouton_pilotes_pret()

        conseils = analyse.conseils(resultat)
        if bilan is None:
            self._remplacer_conseils([], resultat["erreurs"]["score"], animer=animer)
        elif conseils:
            self._remplacer_conseils(conseils, liens=bilan["liens"], animer=animer)
        elif note is None:  # pas de conseil, mais une partie n'a pas pu être vérifiée
            self._remplacer_conseils([], "Aucun conseil pour les parties vérifiées, mais l'analyse est incomplète.",
                                     animer=animer)
        else:
            self._remplacer_conseils([], "Rien à signaler : ton PC est en bonne forme.", animer=animer)

        if resultat["historique"] is None:
            self._texte_comparaison([f"L'historique n'a pas pu être lu ou enregistré. {analyse.AIDE}"])
        elif note is None:
            self._texte_comparaison(["Analyse incomplète : elle n'est pas enregistrée dans l'historique."])
            self.graphique.afficher(historique.serie(resultat["historique"]), animer)
        else:
            self._texte_comparaison(resultat["comparaison"])
            self.graphique.afficher(historique.serie(resultat["historique"]), animer)

        self.progression.hide()
        self.bouton.setText("  Relancer l'analyse")
        self.bouton.setEnabled(True)
        self.bilan_en_cours = False
        self._autoriser_mode()
        self.copier.setEnabled(True)
        self.enregistrer.setEnabled(True)

    def afficher_historique_existant(self) -> None:
        """Au lancement : le graphique des analyses précédentes, s'il y en a."""
        try:
            entrees = historique.charger()
            self.graphique.afficher(historique.serie(entrees))
        except Exception:  # un historique illisible ne doit pas empêcher l'ouverture
            journal.exception("Historique illisible au lancement")
            entrees = []
        self._texte_comparaison(["Lance une analyse pour voir ce qui a changé depuis la dernière fois."]
                                if entrees else ["Aucune analyse enregistrée pour l'instant."])

    # --- Actions ---

    def effacer_historique(self) -> None:
        feuille = Feuille(self, "Effacer l'historique ?", "Toutes les analyses enregistrées seront effacées.",
                          "Cette action est définitive.", confirmer="Effacer", destructif=True, icone="effacer")
        if feuille.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            historique.effacer()
        except OSError:
            journal.exception("Impossible d'effacer l'historique")
            self.annonce.montrer("L'historique n'a pas pu être effacé.", "erreur")
            return
        self.graphique.afficher([])
        self._texte_comparaison(["Historique effacé."])
        self.annonce.montrer("Historique effacé.", "valide")

    def vider_corbeille(self) -> None:
        """Une des rares actions qui modifient le PC (voir CLAUDE.md), seulement sur ce clic : Windows demande lui-même
        confirmation."""
        try:
            avant = fichiers.corbeille()
            fichiers.vider_corbeille(int(self.winId()))
            # Fichiers temporaires et caches inchangés : les remesurer figerait la fenêtre.
            module = fichiers.scan(self.resultat["modules"]["fichiers"])
        except Exception:
            journal.exception("Impossible de vider la Corbeille")
            self.annonce.montrer("La Corbeille n'a pas pu être vidée.", "erreur")
            return
        libere = avant - module["corbeille"]
        if libere <= 0:  # confirmation refusée
            self.annonce.montrer("La Corbeille n'a pas été vidée.")
            return
        self.resultat["modules"]["fichiers"] = module
        self.cartes["fichiers"].remplir(analyse.points_module(self.resultat, "fichiers"), None, module["constats"],
                                        [], None)
        self._bouton_vider_pret(bool(module["corbeille"]))
        self.annonce.montrer(f"Corbeille vidée : {taille_lisible(libere)} libérés. "
                             "Relance l'analyse pour mettre le score à jour.", "valide", 6000)

    def _autoriser_mode(self) -> None:
        """Le changement de mode recrée tout le contenu : pas pendant une analyse, qui perdrait son affichage."""
        self.mode.setEnabled(not self.bilan_en_cours and not self.stockage.en_cours()
                             and not self.connexion.en_cours() and self.telechargement is None
                             and self.pilotes_a_installer is None)

    def changer_page(self, numero: int) -> None:
        """Onglets : la nouvelle page apparaît en fondu rapide sur l'ancienne."""
        self.groupe_onglets.button(numero).setChecked(True)  # aussi quand on arrive par un lien
        if numero == self.pages.currentIndex():
            return
        fondu = Fondu(self, self.grab(), DUREE_ONGLET)
        self.onglet = numero
        self.pages.setCurrentIndex(numero)
        self._suivre_page()
        fondu.hide()  # l'image de la nouvelle page, sans le fondu par-dessus
        nouvelle = self.grab()
        fondu.show()
        fondu.demarrer(nouvelle)

    def changer_mode(self) -> None:
        """Bouton clair/sombre : retient le choix, puis recrée le contenu avec les nouvelles couleurs."""
        try:
            theme.enregistrer_mode(not theme.CLAIR)
        except OSError:
            journal.exception("Impossible d'enregistrer le mode d'affichage")
            self.annonce.montrer("Le mode d'affichage n'a pas pu être changé.", "erreur")
            return
        # L'image de l'affichage actuel couvre la fenêtre : la suite se prépare dessous, sans rien montrer.
        fondu = Fondu(self, self.grab(), DUREE_FONDU)
        # Hors du clic : le bouton qui vient d'être cliqué fait partie du contenu remplacé.
        QTimer.singleShot(0, lambda: self._preparer_fondu(fondu))

    def _preparer_fondu(self, fondu: Fondu) -> None:
        """Recrée le contenu avec les nouvelles couleurs, sous l'image de l'ancien."""
        anciennes = couleurs_cadre()
        positions = [self.pages.widget(numero).verticalScrollBar().value() for numero in range(self.pages.count())]
        self.resultat_stockage, self.racine_stockage = self.stockage.resultat, self.stockage.racine
        self.doublons_stockage = self.stockage.doublons
        self.resultat_connexion = self.connexion.resultat
        self.stockage.arreter()  # analyse finie, mais son thread peut vivre encore un instant
        self.connexion.arreter()
        # Ancien contenu supprimé tout de suite : la nouvelle feuille de style n'a pas à le restyler.
        self.takeCentralWidget()
        importlib.reload(theme)  # les couleurs sont des constantes du module : on le relit pour les recalculer
        appliquer_couleurs(QApplication.instance())
        self.construire()
        fondu.raise_()
        # Au tour suivant de Qt (tailles calculées) : même position, image du nouvel affichage, fondu.
        QTimer.singleShot(0, lambda: self._fondre(fondu, positions, anciennes))

    def _fondre(self, fondu: Fondu, positions: list[int], anciennes: tuple[QColor, QColor, QColor]) -> None:
        """Lance le fondu ; la barre de titre et le liseré suivent le même mélange de couleurs, étape par étape."""
        for numero, position in enumerate(positions):  # chaque onglet reste au même endroit
            self.pages.widget(numero).verticalScrollBar().setValue(position)
        fondu.hide()
        nouvelle = self.grab()
        fondu.show()
        nouvelles = couleurs_cadre()
        bascule = [False]

        def avancer(progres: float) -> None:
            colorer_barre_titre(self, *(melange(nouvelle_, ancienne, progres)
                                        for nouvelle_, ancienne in zip(nouvelles, anciennes)))
            if progres >= 0.5 and not bascule[0]:  # boutons réduire/fermer : ils ne savent que basculer
                bascule[0] = True
                boutons_barre_titre(self, sombres=not theme.CLAIR)

        fondu.animation.valueChanged.connect(avancer)
        fondu.animation.finished.connect(lambda: mode_barre_titre(QApplication.instance()))  # Qt au même mode
        fondu.demarrer(nouvelle)

    def ouvrir(self, cible: str) -> None:
        """Bouton « Ouvrir » d'un conseil : la page des Paramètres, le dossier ou l'outil, sans rien modifier.

        Seule exception, le conseil des pilotes : son bouton lance leur mise à jour, après confirmation."""
        if cible == score.ACTION_PILOTES:
            self.mettre_a_jour_pilotes()
            return
        try:
            os.startfile(cible)  # comme un double-clic
        except OSError:
            journal.exception("Impossible d'ouvrir %s", cible)
            self.annonce.montrer("Cette page n'a pas pu s'ouvrir sur ce PC.", "erreur")

    def copier_rapport(self) -> None:
        if not self.resultat:
            return
        QGuiApplication.clipboard().setText(analyse.rapport_texte(self.resultat))
        # Confirmation sur le bouton lui-même, le temps d'un coup d'œil (même largeur : rien ne bouge autour).
        bouton_copier = self.copier
        bouton_copier.setMinimumWidth(bouton_copier.width())
        bouton_copier.setText(" Rapport copié")
        bouton_copier.setIcon(theme.icone("valide", theme.NIVEAUX["vert"]))
        QTimer.singleShot(1600, bouton_copier, lambda: (bouton_copier.setText(" Copier le rapport"),
                                                        bouton_copier.setIcon(theme.icone("copier"))))

    def enregistrer_rapport(self) -> None:
        """Écrit le rapport HTML uniquement à l'endroit choisi dans la boîte de dialogue."""
        if not self.resultat:
            return
        dossier = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        nom = f"{dossier}/bilan-sante-pc-{self.resultat['date']:%Y-%m-%d}.html"
        chemin, _ = QFileDialog.getSaveFileName(self, "Enregistrer le rapport", nom, "Page web (*.html)")
        if not chemin:
            return  # annulé : aucun fichier créé
        try:
            page = analyse.rapport_html(self.resultat)  # avant d'ouvrir : jamais de fichier vide en cas d'échec
            with open(chemin, "w", encoding="utf-8") as fichier:
                fichier.write(page)
        except Exception:
            journal.exception("Impossible d'enregistrer le rapport")
            Feuille(self, "Rapport non enregistré", "Le rapport n'a pas pu être enregistré à cet endroit.",
                    "Essaie un autre dossier.", confirmer="OK", annuler=None, icone="avertissement").exec()
            return
        self.annonce.montrer("Rapport enregistré.", "valide")

    # --- Mises à jour ---

    def verifier_mise_a_jour(self) -> None:
        """Peu après l'ouverture : cherche en arrière-plan une nouvelle version publiée sur GitHub (rien ne s'affiche
        s'il n'y en a pas, ou hors ligne)."""
        self.recherche = Travail(lambda _avance, _arret: mise_a_jour.verifier(),
                                 "La recherche de mise à jour a échoué.")
        self.recherche.termine.connect(self._nouvelle_version)
        self.recherche.start()

    def _nouvelle_version(self, nouvelle: dict | None) -> None:
        if not nouvelle or "erreur" in nouvelle:
            return
        self.nouvelle_version = nouvelle
        self._montrer_mise_a_jour()
        apparaitre(self.bouton_maj)
        self.annonce.montrer(f"Une nouvelle version de Bilan santé PC est disponible : la {nouvelle['version']}.",
                             duree=6000)

    def _montrer_mise_a_jour(self) -> None:
        """Le bouton « Mettre à jour » de la barre du haut, seulement quand une nouvelle version est publiée."""
        self.bouton_maj.setVisible(self.nouvelle_version is not None)
        if self.nouvelle_version:
            self.bouton_maj.setToolTip(f"Version {self.nouvelle_version['version']} disponible "
                                       f"(tu as la {config.VERSION})")

    def proposer_mise_a_jour(self) -> None:
        """Bouton « Mettre à jour » : les nouveautés, puis, sur confirmation, le téléchargement et l'installation (ou
        la page de la version, si elle ne peut pas s'installer toute seule)."""
        nouvelle = self.nouvelle_version
        notes = mise_a_jour.notes_lisibles(nouvelle["notes"])
        texte = f"Tu as la version {config.VERSION}." + (f" Nouveautés :\n{notes}" if notes else "")
        if mise_a_jour.installable(nouvelle):
            details = ("L'application télécharge la nouvelle version depuis GitHub, se ferme puis se rouvre toute "
                       "seule. Ton historique et tes réglages sont gardés.")
            confirmer = "Mettre à jour"
        else:
            details = ("Elle ne peut pas s'installer toute seule ici : télécharge son installation depuis sa page sur "
                       "GitHub, puis lance-la.")
            confirmer = "Ouvrir la page"
        feuille = Feuille(self, f"Version {nouvelle['version']} disponible", texte, details, confirmer=confirmer,
                          annuler="Plus tard", icone="telechargement")
        if feuille.exec() != QDialog.DialogCode.Accepted:
            return
        if confirmer == "Mettre à jour":
            self.telecharger_mise_a_jour()
        else:
            self.ouvrir(nouvelle["page"])

    def telecharger_mise_a_jour(self) -> None:
        """Télécharge et vérifie la nouvelle version en arrière-plan ; le bouton montre où en est le téléchargement."""
        nouvelle, dossier = self.nouvelle_version, mise_a_jour.dossier_application()

        def preparer(avance, arret) -> dict | None:
            installateur = mise_a_jour.preparer(nouvelle["installateur"], dossier, avance, arret)
            return installateur and {"installateur": installateur}

        self.telechargement = Travail(preparer, "La mise à jour n'a pas pu être téléchargée.", discret=False)
        self.telechargement.avance.connect(lambda valeurs: self.bouton_maj.setText(f" {round(valeurs[0] * 100)} %"))
        self.telechargement.termine.connect(self._installer)
        self.bouton_maj.setMinimumWidth(self.bouton_maj.width())  # même largeur pendant le téléchargement
        self.bouton_maj.setEnabled(False)
        self.bouton_maj.setText(" 0 %")
        self._autoriser_mode()
        self.annonce.montrer(f"Téléchargement de la version {nouvelle['version']}…")
        self.telechargement.start()

    def _installer(self, resultat: dict | None) -> None:
        """Installateur téléchargé : il se lance et l'application se ferme pour le laisser remplacer ses fichiers (il
        rouvre l'application ensuite)."""
        self.telechargement.wait()
        self.telechargement = None
        if resultat is None:  # arrêté : l'application se ferme
            return
        if "erreur" not in resultat:
            try:
                mise_a_jour.lancer_installation(resultat["installateur"], mise_a_jour.dossier_application())
            except OSError:
                journal.exception("Impossible de lancer l'installation de la mise à jour")
                resultat = {"erreur": f"La mise à jour n'a pas pu s'installer. {analyse.AIDE}"}
            else:
                self.close()
                return
        self.bouton_maj.setText(" Mettre à jour")
        self.bouton_maj.setEnabled(True)
        self._autoriser_mode()
        self.annonce.montrer(resultat["erreur"], "erreur", 8000)

    # --- Pilotes ---

    def _bouton_pilotes_pret(self) -> None:
        """« Mettre à jour les pilotes » : seulement s'il y a des pilotes à installer, ou pendant leur installation."""
        module = self.resultat and self.resultat["modules"].get("pilotes")
        a_installer = bool(module and module["a_installer"])
        self.bouton_pilotes.setText(" Mettre à jour les pilotes")
        self.bouton_pilotes.setVisible(a_installer or self.pilotes_a_installer is not None)
        self.bouton_pilotes.setEnabled(a_installer and self.pilotes_a_installer is None)

    def mettre_a_jour_pilotes(self) -> None:
        """Bouton « Mettre à jour les pilotes » (carte Pilotes ou conseil) : après confirmation, télécharge le pilote
        NVIDIA, puis installe tout en administrateur (Windows demande l'autorisation)."""
        module = self.resultat and self.resultat["modules"].get("pilotes")
        if not module or self.pilotes_a_installer is not None:
            return
        if not module["a_installer"]:
            self.annonce.montrer("Les pilotes ont déjà été mis à jour : relance l'analyse pour vérifier.")
            return
        nvidia = module["nvidia"] if pilotes.nvidia_a_installer(module["nvidia"]) else None
        mises_a_jour = module["mises_a_jour"] or []
        lignes = [f"• Pilote NVIDIA {nvidia['derniere']['version']}, téléchargé depuis le site de NVIDIA "
                  f"({taille_lisible(nvidia['derniere']['taille'])})"] if nvidia else []
        lignes += [f"• {mise_a_jour['nom']}, par Windows Update" for mise_a_jour in mises_a_jour]
        details = ("Windows va demander ton autorisation." + (" Pendant l'installation du pilote NVIDIA, l'écran peut "
                   "clignoter ou devenir noir quelques secondes." if nvidia else "")
                   + " Un redémarrage peut être demandé à la fin.")
        feuille = Feuille(self, "Mettre à jour les pilotes ?", "\n".join(lignes), details, confirmer="Mettre à jour",
                          icone="telechargement")
        if feuille.exec() != QDialog.DialogCode.Accepted:
            return
        self.pilotes_a_installer = {"nvidia": nvidia, "mises_a_jour": mises_a_jour}
        self.bouton_pilotes.setMinimumWidth(self.bouton_pilotes.width())  # même largeur pendant l'installation
        self.bouton_pilotes.setEnabled(False)
        self._autoriser_mode()
        if not nvidia:
            self._installer_pilotes(None)
            return

        def telecharger(avance, arret) -> dict | None:
            paquet = installation_pilotes.telecharger_nvidia(nvidia["derniere"], avance, arret)
            return paquet and {"paquet": paquet}

        self.travail_pilotes = Travail(telecharger, "Le pilote NVIDIA n'a pas pu être téléchargé.", discret=False)
        self.travail_pilotes.avance.connect(
            lambda valeurs: self.bouton_pilotes.setText(f" {round(valeurs[0] * 100)} %"))
        self.travail_pilotes.termine.connect(self._pilote_nvidia_telecharge)
        self.bouton_pilotes.setText(" 0 %")
        self.annonce.montrer(f"Téléchargement du pilote NVIDIA {nvidia['derniere']['version']}…")
        self.travail_pilotes.start()

    def _pilote_nvidia_telecharge(self, resultat: dict | None) -> None:
        self.travail_pilotes.wait()
        self.travail_pilotes = None
        if resultat is None:  # arrêté : l'application se ferme
            return
        if "erreur" in resultat:
            self._fin_pilotes()
            self.annonce.montrer(resultat["erreur"], "erreur", 8000)
            return
        self._installer_pilotes(resultat["paquet"])

    def _installer_pilotes(self, paquet) -> None:
        """Lance l'installation en administrateur, puis la suit toutes les demi-secondes."""
        ids = [mise_a_jour["id"] for mise_a_jour in self.pilotes_a_installer["mises_a_jour"]]
        self.bouton_pilotes.setText(" Autorisation…")
        try:
            self.processus_pilotes = installation_pilotes.lancer(ids, paquet, int(self.winId()))
        except installation_pilotes.Annulee:
            self._fin_pilotes()
            self.annonce.montrer("Mise à jour des pilotes annulée : l'autorisation n'a pas été donnée.")
            return
        except (OSError, ValueError):
            journal.exception("Impossible de lancer l'installation des pilotes")
            self._fin_pilotes()
            self.annonce.montrer(f"L'installation des pilotes n'a pas pu démarrer. {analyse.AIDE}", "erreur", 8000)
            return
        self.bouton_pilotes.setText(" Installation…")
        self.annonce.montrer("Installation des pilotes en cours : ça peut prendre quelques minutes.", duree=8000)
        self.suivi_pilotes.start()

    def _suivre_pilotes(self) -> None:
        etape = installation_pilotes.lire_etat().get("etape")
        texte = {"windows_update": " Windows Update…", "nvidia": " Pilote NVIDIA…"}.get(etape)
        if texte:
            self.bouton_pilotes.setText(texte)
        if not installation_pilotes.termine(self.processus_pilotes):
            return
        self.suivi_pilotes.stop()
        self.processus_pilotes = None
        a_installer = self.pilotes_a_installer
        resultat = installation_pilotes.bilan(installation_pilotes.lire_etat(), a_installer["mises_a_jour"],
                                              a_installer["nvidia"])
        installation_pilotes.nettoyer()
        if resultat["installes"] and not resultat["echecs"]:
            self.resultat["modules"]["pilotes"]["a_installer"] = 0  # à jour jusqu'à la prochaine analyse
        self._fin_pilotes()
        self._annoncer_pilotes(resultat)

    def _annoncer_pilotes(self, resultat: dict) -> None:
        installes = " et ".join(resultat["installes"])
        if resultat["installes"] and resultat["redemarrage"]:
            Feuille(self, "Redémarre le PC pour finir", f"Installé : {installes}.",
                    " ".join(resultat["echecs"] + ["Windows utilisera les nouveaux pilotes après le redémarrage."]),
                    annuler=None, icone="valide").exec()
        elif resultat["installes"]:
            self.annonce.montrer(f"Installé : {installes}. {' '.join(resultat['echecs'])} "
                                 "Relance l'analyse pour voir le résultat.", "valide", 8000)
        else:
            self.annonce.montrer(f"{' '.join(resultat['echecs'])} {analyse.AIDE}", "erreur", 10000)

    def _fin_pilotes(self) -> None:
        self.pilotes_a_installer = None
        self.bouton_pilotes.setMinimumWidth(0)
        self._bouton_pilotes_pret()
        self._autoriser_mode()

    def closeEvent(self, evenement) -> None:
        # Fermer pendant une analyse : on cache la fenêtre puis on attend la fin des threads,
        # sinon Qt plante en détruisant un thread encore actif. Le stockage, le test de connexion et le téléchargement
        # d'une mise à jour s'arrêtent en route.
        travaux = [travail for travail in (self.analyse, self.recherche, self.telechargement, self.travail_pilotes)
                   if travail and travail.isRunning()]
        if travaux or self.stockage.en_cours() or self.connexion.en_cours():
            self.hide()
        self.stockage.arreter()
        self.connexion.arreter()
        if self.telechargement:
            self.telechargement.arret.set()
        if self.travail_pilotes:  # l'installation en administrateur, elle, va au bout même si l'application se ferme
            self.travail_pilotes.arret.set()
        for travail in travaux:
            travail.wait()
        super().closeEvent(evenement)


@cache  # chargée une fois : appelée à chaque étape du fondu
def _dwm_attribut():
    fonction = ctypes.WinDLL("dwmapi").DwmSetWindowAttribute
    fonction.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    return fonction


def couleurs_cadre() -> tuple[QColor, QColor, QColor]:
    """Fond et texte de la barre de titre, et liseré de la fenêtre, aux couleurs du mode actuel."""
    return QColor(theme.FOND), QColor(theme.TEXTE), QColor(theme.BORD_FENETRE)


def colorer_barre_titre(fenetre: QWidget, fond: QColor, texte: QColor, bord: QColor) -> None:
    """Couleurs de la barre de titre et du liseré dessinés par Windows 11 (sans effet sur Windows 10)."""
    for attribut, couleur in ((DWMWA_CAPTION_COLOR, fond), (DWMWA_TEXT_COLOR, texte), (DWMWA_BORDER_COLOR, bord)):
        colorref = wintypes.DWORD(couleur.red() | couleur.green() << 8 | couleur.blue() << 16)  # 0x00BBGGRR
        _dwm_attribut()(int(fenetre.winId()), attribut, ctypes.byref(colorref), ctypes.sizeof(colorref))


class _OptionsTheme(ctypes.Structure):
    _fields_ = [("dwFlags", wintypes.DWORD), ("dwMask", wintypes.DWORD)]


def epurer_barre_titre(fenetre: QWidget) -> None:
    """Barre de titre de Windows sans titre ni icône : la barre du haut de l'application les montre déjà.

    Elle se fond alors dans la barre du haut ; le nom reste dans la barre des tâches et pour les lecteurs d'écran.
    """
    sans = WTNCA_NODRAWCAPTION | WTNCA_NODRAWICON
    options = _OptionsTheme(sans, sans)
    ctypes.WinDLL("uxtheme").SetWindowThemeAttribute(wintypes.HWND(int(fenetre.winId())), WTA_NONCLIENT,
                                                     ctypes.byref(options), ctypes.sizeof(options))


def boutons_barre_titre(fenetre: QWidget, sombres: bool) -> None:
    """Boutons réduire/fermer en version sombre ou claire, directement auprès de Windows.

    Passer par Qt (mode_barre_titre) réappliquerait le style à toute la fenêtre : un à-coup en plein fondu.
    """
    valeur = wintypes.BOOL(sombres)
    _dwm_attribut()(int(fenetre.winId()), DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(valeur),
                    ctypes.sizeof(valeur))


def mode_barre_titre(app: QApplication) -> None:
    """Boutons de la barre de titre (réduire, fermer) clairs ou sombres comme le thème."""
    app.styleHints().setColorScheme(Qt.ColorScheme.Light if theme.CLAIR else Qt.ColorScheme.Dark)


def preparer_application(app: QApplication) -> None:
    """Style Fusion, police, palette et feuille de style du mode, icône de l'application et infobulles."""
    app.setStyle("Fusion")
    app.setFont(theme.police("corps"))
    app.setWindowIcon(QIcon(str(theme.ICONE_APPLICATION)))  # vaut pour toutes les fenêtres, dialogues compris
    appliquer_couleurs(app)
    Infobulle.instance()  # toutes les infobulles dans le style de l'application, jamais la bulle grise de Qt


def appliquer_couleurs(app: QApplication) -> None:
    """Palette et feuille de style du mode actuel (seules à changer entre clair et sombre)."""
    palette = QPalette()
    for role, couleur in ((QPalette.ColorRole.Window, theme.FOND), (QPalette.ColorRole.WindowText, theme.TEXTE),
                          (QPalette.ColorRole.Base, theme.SURFACE), (QPalette.ColorRole.Text, theme.TEXTE),
                          (QPalette.ColorRole.Button, theme.SURFACE), (QPalette.ColorRole.ButtonText, theme.TEXTE),
                          (QPalette.ColorRole.Highlight, theme.ACCENT), (QPalette.ColorRole.HighlightedText, "white"),
                          (QPalette.ColorRole.PlaceholderText, theme.TEXTE_3)):
        palette.setColor(role, QColor(couleur))
    app.setPalette(palette)
    app.setFont(theme.police("corps"))  # après un changement de mode, le module du thème est relu
    app.setStyleSheet(theme.STYLE)


def lancer_interface() -> int:
    app = QApplication(sys.argv)
    preparer_application(app)
    mode_barre_titre(app)
    fenetre = Fenetre()
    fenetre.show()
    journal.info("Fenêtre ouverte")
    if mise_a_jour.ARGUMENT_FAITE in sys.argv:  # rouverte par le mode installation d'une mise à jour
        QTimer.singleShot(400, lambda: fenetre.annonce.montrer(
            f"Bilan santé PC est à jour : version {config.VERSION}.", "valide", 6000))
    elif mise_a_jour.ARGUMENT_RATEE in sys.argv:
        QTimer.singleShot(400, lambda: fenetre.annonce.montrer(
            f"La mise à jour n'a pas pu s'installer : l'ancienne version est restée en place. {analyse.AIDE}",
            "erreur", 10000))
    QTimer.singleShot(DELAI_RECHERCHE, fenetre.verifier_mise_a_jour)
    return app.exec()
