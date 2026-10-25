"""Page Connexion : la liaison du PC avec la box, lue auprès de Windows, et un test de débit réel (PySide6).

Le test est la seule partie de l'application qui utilise le réseau, et seulement sur clic : il échange des données
de test avec les serveurs de Cloudflare, rien d'autre (voir modules/connexion.py).
"""

import time
from typing import Callable

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from modules import connexion
from ui import theme
from ui.stockage import Travail, carte_liste, titre, vider
from ui.verre import Page, Verre
from ui.widgets import CarteConseil, TuileIcone, apparaitre, bouton, pastille, pied_de_page, repolir

# Part de la barre de progression (en millièmes) occupée par chaque étape du test : (début, fin).
ETAPES = {"ping": (0, 100), "descendant": (100, 550), "montant": (550, 1000)}
TEXTES_ETAPES = {"ping": "Mesure du ping…", "descendant": "Mesure du téléchargement…", "montant": "Mesure de l'envoi…"}
FRAICHEUR_LIAISON = 5  # secondes : en revenant sur l'onglet plus tard, la liaison est relue
TEXTE_AVANT = "Le test dure une vingtaine de secondes. Seules des données de test passent par internet."
TEXTE_AIDE = ("Le test mesure le ping, puis télécharge et envoie des données de test avec le serveur de Cloudflare le "
              "plus proche (speed.cloudflare.com). Seules ces données de test passent par internet : ni tes fichiers, "
              "ni le bilan de ton PC. Le test utilise d'autant plus de données que la connexion est rapide (jusqu'à "
              "350 Mo sur la fibre) : évite-le sur un forfait mobile limité. Pour un résultat juste, mets en pause "
              "les téléchargements en cours.")


class Compteur(QWidget):
    """Une mesure du test : tuile d'icône et nom, la valeur en grand avec son unité, et ce qu'elle veut dire."""

    def __init__(self, icone: str, teinte: str, nom: str, unite: str, sens: str) -> None:
        super().__init__()
        self.valeur = QLabel("–", font=theme.police("grand"))
        unite_ = QLabel(unite, objectName="secondaire")
        # Unité posée sur la même ligne de base que le chiffre (le grand chiffre descend plus bas sous la ligne).
        unite_.setContentsMargins(0, 0, 0, QFontMetrics(self.valeur.font()).descent()
                                  - QFontMetrics(unite_.font()).descent())
        entete = QHBoxLayout()
        entete.setSpacing(8)
        entete.addWidget(TuileIcone(icone, teinte, 24))
        entete.addWidget(QLabel(nom, font=theme.police("fort")))
        entete.addStretch()
        chiffre = QHBoxLayout()
        chiffre.setSpacing(6)
        chiffre.addWidget(self.valeur, alignment=Qt.AlignmentFlag.AlignBottom)
        chiffre.addWidget(unite_, alignment=Qt.AlignmentFlag.AlignBottom)
        chiffre.addStretch()
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.setSpacing(6)
        disposition.addLayout(entete)
        disposition.addLayout(chiffre)
        disposition.addWidget(QLabel(sens, objectName="discret", font=theme.police("legende")))
        self.nom, self.unite = nom, unite
        self.definir("–")

    def definir(self, texte: str) -> None:
        self.valeur.setText(texte)
        self.setAccessibleName(f"{self.nom} : {texte} {self.unite}" if texte != "–" else f"{self.nom} : pas mesuré")


def ligne(gauche: QWidget | str, droite: QWidget | str, detail: str = "") -> QWidget:
    """Ligne d'une carte en liste : un texte à gauche (et sa précision dessous), une valeur à droite."""
    textes = QVBoxLayout()
    textes.setSpacing(2)
    textes.addWidget(QLabel(gauche) if isinstance(gauche, str) else gauche)
    if detail:
        textes.addWidget(QLabel(detail, objectName="discret", wordWrap=True, font=theme.police("legende")))
    resultat = QWidget()
    disposition = QHBoxLayout(resultat)
    disposition.setContentsMargins(12, 9, 12, 9)
    disposition.setSpacing(12)
    disposition.addLayout(textes, 1)
    disposition.addWidget(QLabel(droite, font=theme.police("fort")) if isinstance(droite, str) else droite,
                          alignment=Qt.AlignmentFlag.AlignVCenter)
    return resultat


class PageConnexion(Page):
    """Contenu de l'onglet Connexion. La fenêtre le place dans une zone de défilement."""

    statut = Signal(str, str)  # message à annoncer et sa nature (« info », « valide » ou « erreur »)
    occupee = Signal(bool)  # test en cours : la fenêtre bloque le changement de mode clair/sombre

    def __init__(self, ouvrir: Callable[[str], None], resultat: dict | None = None) -> None:
        super().__init__()
        self.ouvrir = ouvrir
        self.resultat = resultat
        # Comme pour le stockage, les threads sont gardés après leur fin (Qt plante s'il en détruit un encore actif).
        self.travail: Travail | None = None  # le test
        self.lecture: Travail | None = None  # la liaison avec la box, relue à chaque visite de l'onglet
        self.lue_a = float("-inf")
        self.occupe = False

        disposition = self.disposition
        disposition.addWidget(self._heros())
        self.sections = []  # montrées seulement après un test réussi
        cadre_usages, self.liste_usages = carte_liste()
        self.liste_conseils = QVBoxLayout()
        self.liste_conseils.setSpacing(10)
        conseils = QWidget()
        conseils.setLayout(self.liste_conseils)
        self.liste_conseils.setContentsMargins(0, 0, 0, 0)
        for intitule, contenu in ((titre("Ce que ta connexion permet"), cadre_usages),
                                  (titre("Conseils"), conseils)):
            disposition.addWidget(intitule)
            disposition.addWidget(contenu)
            self.sections += [intitule, contenu]
        cadre_liaison, self.liste_liaison = carte_liste()
        disposition.addWidget(titre("Ta liaison avec la box"))
        disposition.addWidget(cadre_liaison)
        disposition.addWidget(self._aide())
        disposition.addWidget(pied_de_page())
        disposition.addStretch()

        self.liste_liaison.addWidget(ligne("Connexion", "…"))
        if resultat:
            self.afficher(resultat, animer=False)  # même test : rien ne se re-remplit
        else:
            self._sans_resultat()

    # --- Construction ---

    def _heros(self) -> Verre:
        self.etat = pastille()
        self.phrase = QLabel(wordWrap=True, font=theme.police("titre"))
        self.compteurs = {"descendant": Compteur("telechargement", "bleu", "Téléchargement", "Mbit/s",
                                                 "Ce que tu reçois : pages, vidéos, jeux"),
                          "montant": Compteur("envoi", "violet", "Envoi", "Mbit/s",
                                              "Ce que tu envoies : photos, appels vidéo"),
                          "ping": Compteur("ping", "aqua", "Ping", "ms", "Temps de réaction de la connexion")}
        chiffres = QHBoxLayout()
        chiffres.setSpacing(24)
        for compteur in self.compteurs.values():
            chiffres.addWidget(compteur, 1)
        self.info = QLabel(objectName="secondaire", wordWrap=True)
        self.remarque = QLabel(objectName="secondaire", wordWrap=True, font=theme.police("legende"))
        self.bouton = bouton("", "principal", "connexion", "white", 15, font=theme.police("fort"))
        self.bouton.clicked.connect(self.lancer)
        self.progression = QProgressBar(textVisible=False, maximum=1000)
        self.progression.hide()
        self.glissement = QPropertyAnimation(self.progression, b"value", self.progression, duration=300,
                                             easingCurve=QEasingCurve.Type.OutCubic)

        cadre = Verre(rayon=26)
        disposition = QVBoxLayout(cadre)
        disposition.setContentsMargins(28, 22, 28, 24)
        disposition.setSpacing(10)
        disposition.addWidget(self.etat, alignment=Qt.AlignmentFlag.AlignLeft)
        disposition.addWidget(self.phrase)
        disposition.addSpacing(10)
        disposition.addLayout(chiffres)
        disposition.addSpacing(6)
        disposition.addWidget(self.info)
        disposition.addWidget(self.remarque)
        disposition.addSpacing(8)
        disposition.addWidget(self.bouton, alignment=Qt.AlignmentFlag.AlignLeft)
        disposition.addWidget(self.progression)
        return cadre

    def _aide(self) -> Verre:
        cadre = Verre(ombre=False)
        disposition = QVBoxLayout(cadre)
        disposition.setContentsMargins(22, 16, 22, 14)
        disposition.setSpacing(6)
        libelle, cible = connexion.LIEN_RESEAU
        lien = bouton(libelle, "lien", "ouvrir", theme.ACCENT_CLAIR, 12)
        lien.clicked.connect(lambda: self.ouvrir(cible))
        disposition.addWidget(QLabel(TEXTE_AIDE, objectName="secondaire", wordWrap=True))
        disposition.addWidget(lien, alignment=Qt.AlignmentFlag.AlignLeft)
        return cadre

    # --- Affichage ---

    def _etat(self, texte: str, niveau: str) -> None:
        self.etat.setText(texte)
        self.etat.setProperty("niveau", niveau)
        repolir(self.etat)

    def _message(self, texte: str, erreur: bool = False) -> None:
        self.info.setText(texte)
        self.info.setObjectName("erreur" if erreur else "secondaire")
        repolir(self.info)

    def _sans_resultat(self, erreur: str | None = None) -> None:
        """Avant tout test, ou après un test impossible : l'invitation à tester, ou ce qui a empêché le test."""
        self.resultat = None
        self._etat("Test impossible" if erreur else "Pas encore testée", "rouge" if erreur else "gris")
        self.phrase.setText("Mesure la vitesse réelle de ta connexion internet.")
        for compteur in self.compteurs.values():
            compteur.definir("–")
        self._message(erreur or TEXTE_AVANT, erreur=bool(erreur))
        self.remarque.hide()
        self.bouton.setText("  Lancer le test")
        for widget in self.sections:
            widget.hide()

    def afficher(self, resultat: dict, animer: bool = True) -> None:
        self.resultat = resultat
        niveau, mot, phrase = connexion.niveau(resultat)
        self._etat(mot, niveau)
        self.phrase.setText(phrase)
        for sens in ("descendant", "montant"):
            self.compteurs[sens].definir(connexion.nombre_debit(resultat[sens]))
        self.compteurs["ping"].definir(f"{resultat['ping']:.0f}")
        self._message(f"Test du {resultat['date']:%d/%m/%Y à %H:%M} avec le serveur de Cloudflare le plus proche, "
                      f"en {resultat['duree']:.0f} s.")
        remarque = connexion.remarque(resultat)
        self.remarque.setText(remarque or "")
        self.remarque.setVisible(bool(remarque))
        self.bouton.setText("  Relancer le test")
        for widget in self.sections:
            widget.show()

        vider(self.liste_usages)
        for usage, possible in resultat["usages"]:
            self.liste_usages.addWidget(ligne(usage, pastille("Oui" if possible else "Difficile",
                                                              "vert" if possible else "orange")))
        vider(self.liste_conseils)
        for numero, (texte, lien) in enumerate(resultat["conseils"], start=1):
            self.liste_conseils.addWidget(CarteConseil(numero, texte, lien, self.ouvrir))
        if not resultat["conseils"]:
            cadre = Verre(rayon=18)
            message = QVBoxLayout(cadre)
            message.setContentsMargins(20, 16, 20, 16)
            message.addWidget(QLabel("Rien à signaler : rien ne freine ta connexion.", objectName="secondaire",
                                     wordWrap=True))
            self.liste_conseils.addWidget(cadre)
        if animer:
            for position in range(self.liste_conseils.count()):
                apparaitre(self.liste_conseils.itemAt(position).widget(), delai=position * 90)
        self._afficher_liaison(resultat["liaison"])

    def _afficher_liaison(self, lien: dict | None) -> None:
        """Carte « Ta liaison avec la box » ; `lien` None : Windows n'a pas pu la donner."""
        vider(self.liste_liaison)
        lignes = connexion.description(lien) if lien else [("Connexion", "Inconnue",
                                                             "Windows n'a pas pu donner les informations.")]
        for nom, valeur, detail in lignes:
            self.liste_liaison.addWidget(ligne(nom, valeur, detail))

    # --- Liaison avec la box (lue sans rien envoyer) ---

    def showEvent(self, evenement) -> None:
        super().showEvent(evenement)
        if not self.occupe and time.monotonic() - self.lue_a > FRAICHEUR_LIAISON:
            self.lire_liaison()

    def lire_liaison(self) -> None:
        """Relit la liaison en arrière-plan : le service Wi-Fi de Windows met quelques dizaines de ms à répondre."""
        if self.lecture and self.lecture.isRunning():
            return
        if self.lecture:
            self.lecture.wait()
        self.lue_a = time.monotonic()
        self.lecture = Travail(lambda _progression, _arret: connexion.liaison(),
                               "La liaison avec la box n'a pas pu être lue.")
        self.lecture.termine.connect(self._liaison_lue)
        self.lecture.start()

    def _liaison_lue(self, lien: dict) -> None:
        if not self.occupe:  # pendant un test, la carte montrera la liaison relevée par le test
            self._afficher_liaison(None if "erreur" in lien else lien)

    # --- Test (le seul accès au réseau de l'application, sur ce clic) ---

    def en_cours(self) -> bool:
        return self.occupe

    def _occuper(self, occupe: bool) -> None:
        self.occupe = occupe
        self.occupee.emit(occupe)

    def lancer(self) -> None:
        """Lance le test ; pendant le test, le même bouton l'arrête."""
        if self.occupe:
            self.travail.arret.set()
            self.bouton.setEnabled(False)
            self.bouton.setText("  Arrêt en cours…")
            return
        self.arreter()  # le précédent finit tout juste : on attend son thread avant de le remplacer
        self._occuper(True)
        # Pas en priorité basse : un thread freiné fausserait le ping.
        self.travail = Travail(connexion.scan, "Le test de connexion n'a pas pu aboutir.", discret=False)
        self.travail.avance.connect(self.avancer)
        self.travail.termine.connect(self.fin)
        self.travail.start()
        self._etat("Test en cours", "gris")
        for compteur in self.compteurs.values():
            compteur.definir("–")
        self.remarque.hide()
        self.bouton.setText("  Arrêter le test")
        self.glissement.stop()
        self.progression.setValue(0)
        self.progression.show()
        self._message("Connexion au serveur de test…")

    def avancer(self, valeurs: tuple[str, float, float | None]) -> None:
        """La valeur de l'étape en cours s'affiche au fil de la mesure ; la barre avance avec le temps."""
        etape, avance, valeur = valeurs
        debut, fin = ETAPES[etape]
        self.glissement.stop()
        self.glissement.setEndValue(round(debut + (fin - debut) * avance))
        self.glissement.start()
        if valeur is not None:
            self.compteurs[etape].definir(f"{valeur:.0f}" if etape == "ping" else connexion.nombre_debit(valeur))
        self.info.setText(TEXTES_ETAPES[etape])

    def fin(self, resultat: dict | None) -> None:
        self._occuper(False)
        self.progression.hide()
        self.bouton.setEnabled(True)
        if resultat is None:  # arrêté : on garde ce qui était affiché
            self.statut.emit("Test de connexion arrêté.", "info")
            if self.resultat:
                self.afficher(self.resultat, animer=False)
            else:
                self._sans_resultat()
            return
        if "erreur" in resultat:
            self.statut.emit("Le test de connexion n'a pas pu aboutir.", "erreur")
            self._sans_resultat(resultat["erreur"])
            if "liaison" in resultat:
                self._afficher_liaison(resultat["liaison"])
            return
        self.afficher(resultat)

    def arreter(self) -> None:
        """Arrête le test et attend la fin des threads, avant que la page ou les threads soient détruits."""
        if self.travail:
            self.travail.arret.set()
            self.travail.wait()
        if self.lecture:
            self.lecture.wait()
