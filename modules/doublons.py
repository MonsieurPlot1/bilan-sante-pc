"""Module doublons : fichiers et dossiers en double parmi les fichiers personnels.

Lecture seule : on lit le contenu des fichiers pour le comparer, sans rien modifier ni supprimer.
On ne cherche que dans les fichiers personnels (ceux que la page Stockage classe par extension) :
dans Windows, les logiciels et les jeux, des fichiers identiques sont normaux et nécessaires.

Deux fichiers sont en double s'ils ont exactement le même contenu : même taille, puis même début
et même fin, puis même empreinte calculée sur tout le fichier. Deux dossiers sont en double s'ils
contiennent les mêmes fichiers, aux mêmes endroits, avec le même contenu.
"""

import hashlib
import os
import time
from collections import defaultdict
from typing import Callable

from modules.stockage import dans

TAILLE_MIN_FICHIER = 1024**2  # un doublon plus petit ne vaut pas la peine d'être montré
TAILLE_MIN_DOSSIER = 10 * 1024**2
ECHANTILLON = 64 * 1024  # lu au début et à la fin d'un fichier pour la comparaison rapide
BLOC = 1024**2  # lecture du contenu complet, morceau par morceau
NB_GROUPES = 30  # groupes montrés, ceux qui libéreraient le plus de place
INTERVALLE_PROGRESSION = 0.1  # secondes entre deux nouvelles de la progression
# Bibliothèques de logiciels : leurs copies sont normales (chaque logiciel a les siennes) et les supprimer
# casse des programmes. Elles ne sont pas montrées seules, seulement avec un dossier en double.
TECHNIQUES = {".dll", ".pyd", ".sys", ".ocx", ".drv"}

Progression = Callable[[str, int, int], None]  # (étape, fait, total)


class Arret(Exception):
    """L'utilisateur a arrêté la recherche."""


def empreinte_rapide(chemin: str, taille: int) -> bytes:
    """Empreinte du début et de la fin d'un fichier : écarte vite la plupart des fichiers de même taille."""
    calcul = hashlib.blake2b(digest_size=16)
    with open(chemin, "rb") as fichier:
        if taille <= 2 * ECHANTILLON:
            calcul.update(fichier.read())
        else:
            calcul.update(fichier.read(ECHANTILLON))
            fichier.seek(taille - ECHANTILLON)
            calcul.update(fichier.read(ECHANTILLON))
    return calcul.digest()


def empreinte_complete(chemin: str, lus: Callable[[int], None], arret: Callable[[], bool]) -> bytes:
    """Empreinte de tout le contenu d'un fichier. `lus(n)` est appelée après chaque morceau lu."""
    calcul = hashlib.blake2b(digest_size=16)
    with open(chemin, "rb") as fichier:
        while bloc := fichier.read(BLOC):
            if arret():
                raise Arret
            calcul.update(bloc)
            lus(len(bloc))
    return calcul.digest()


class _Empreintes:
    """Empreintes déjà calculées (un fichier n'est lu qu'une fois), avec la progression de la lecture."""

    def __init__(self, progression: Progression, arret: Callable[[], bool]) -> None:
        self.progression, self.arret = progression, arret
        self.rapides: dict[str, bytes | None] = {}
        self.completes: dict[str, bytes | None] = {}
        self.derniere = 0.0

    def signaler(self, etape: str, fait: int, total: int) -> None:
        """Donne des nouvelles de temps en temps (toujours à la fin d'une étape)."""
        if fait >= total or time.perf_counter() - self.derniere >= INTERVALLE_PROGRESSION:
            self.derniere = time.perf_counter()
            self.progression(etape, fait, total)

    def calculer_rapides(self, fichiers: dict[str, int]) -> None:
        a_faire = [chemin for chemin in fichiers if chemin not in self.rapides]
        for numero, chemin in enumerate(a_faire, start=1):
            if self.arret():
                raise Arret
            try:
                self.rapides[chemin] = empreinte_rapide(chemin, fichiers[chemin])
            except OSError:  # fichier ouvert par un autre programme, supprimé entre-temps… : pas comparé
                self.rapides[chemin] = None
            self.signaler("rapide", numero, len(a_faire))

    def calculer_completes(self, fichiers: dict[str, int]) -> None:
        a_faire = [chemin for chemin in fichiers if chemin not in self.completes]
        total, lus = sum(fichiers[chemin] for chemin in a_faire), [0]

        def avancer(octets: int) -> None:
            lus[0] += octets
            self.signaler("contenu", lus[0], total)

        for chemin in a_faire:
            try:
                self.completes[chemin] = empreinte_complete(chemin, avancer, self.arret)
            except OSError:
                self.completes[chemin] = None


def _groupes(cles: dict[str, object]) -> list[list[str]]:
    """Chemins regroupés par clé identique (les clés None ne comptent pas), groupes d'au moins deux."""
    par_cle = defaultdict(list)
    for chemin, cle in cles.items():
        if cle is not None:
            par_cle[cle].append(chemin)
    return [sorted(chemins) for chemins in par_cle.values() if len(chemins) > 1]


def _sans_liens_physiques(chemins: list[str]) -> list[str]:
    """Deux noms pour le même fichier (lien physique) ne prennent qu'une fois la place : un seul est gardé."""
    vus, gardes = set(), []
    for chemin in chemins:
        try:
            infos = os.stat(chemin)
            identite = (infos.st_dev, infos.st_ino)
        except OSError:
            continue
        if identite not in vus:
            vus.add(identite)
            gardes.append(chemin)
    return gardes


class _Arbre:
    """Dossiers personnels : contenu de chacun, en descendant dans les sous-dossiers."""

    def __init__(self, personnels: dict) -> None:
        self.fichiers = personnels["fichiers"]
        self.parents = personnels["parents"]
        self.enfants = defaultdict(list)
        for dossier, parent in self.parents.items():
            self.enfants[parent].append(dossier)
        tous = set(self.fichiers) | set(self.parents) | set(self.parents.values())
        # Du plus profond au moins profond : chaque dossier passe après ses sous-dossiers.
        self.ordre = sorted(tous, key=lambda d: d.rstrip(os.sep).count(os.sep), reverse=True)
        self.complet, self.total, self.forme = {}, {}, {}
        for dossier in self.ordre:
            entrees = [("f", nom, taille) for nom, taille in self.fichiers.get(dossier, [])]
            complet = dossier not in personnels["incomplets"]
            total = sum(taille for _, _, taille in entrees)
            for enfant in self.enfants[dossier]:
                complet = complet and self.complet[enfant]
                total += self.total[enfant]
                entrees.append(("d", os.path.basename(enfant), self.forme[enfant]))
            self.complet[dossier], self.total[dossier] = complet, total
            # Forme : les noms et les tailles de tout ce qu'il contient (sans lire les fichiers).
            self.forme[dossier] = hashlib.blake2b(repr(sorted(entrees)).encode(), digest_size=16).digest()

    def contenu(self, dossier: str) -> list[tuple[str, str, int]]:
        """Tous les fichiers du dossier et de ses sous-dossiers : (chemin relatif, chemin, taille)."""
        resultat, pile = [], [(dossier, "")]
        while pile:
            courant, relatif = pile.pop()
            for nom, taille in self.fichiers.get(courant, []):
                resultat.append((os.path.join(relatif, nom), os.path.join(courant, nom), taille))
            for enfant in self.enfants[courant]:
                pile.append((enfant, os.path.join(relatif, os.path.basename(enfant))))
        return sorted(resultat)

    def dans(self, chemin: str, dossiers: set[str]) -> bool:
        """Vrai si `chemin` est à l'intérieur de l'un des `dossiers`."""
        parent = self.parents.get(chemin, os.path.dirname(chemin))
        while parent:
            if parent in dossiers:
                return True
            suivant = self.parents.get(parent)
            parent = suivant if suivant != parent else None
        return False


def _a_lire(dossiers: list[list[str]], fichiers: list[list[str]], contenus: dict) -> set[str]:
    """Tous les fichiers à lire : ceux des dossiers candidats et les fichiers candidats."""
    return ({chemin for groupe in dossiers for d in groupe for _, chemin, _ in contenus[d]}
            | {chemin for groupe in fichiers for chemin in groupe})


def _signature(contenu: list[tuple[str, str, int]], empreintes: dict[str, bytes | None]) -> bytes | None:
    """Empreinte d'un dossier à partir de celles de ses fichiers ; None si l'un d'eux n'a pas pu être lu."""
    parties = []
    for relatif, chemin, taille in contenu:
        if empreintes.get(chemin) is None:
            return None
        parties.append((relatif, taille, empreintes[chemin]))
    return hashlib.blake2b(repr(parties).encode(), digest_size=16).digest()


def _par_signature(groupes: list[list[str]], contenus: dict, empreintes: dict) -> list[list[str]]:
    """Dossiers d'un même groupe re-répartis selon l'empreinte de leur contenu."""
    return [g for groupe in groupes for g in _groupes({d: _signature(contenus[d], empreintes) for d in groupe})]


def _par_empreinte(groupes: list[list[str]], tailles: dict[str, int], empreintes: dict) -> list[list[str]]:
    """Fichiers d'un même groupe re-répartis selon leur empreinte."""
    return [g for groupe in groupes
            for g in _groupes({c: (tailles[c], empreintes[c]) if empreintes[c] else None for c in groupe})]


def chercher(personnels: dict, progression: Progression = lambda *_: None,
             arret: Callable[[], bool] = lambda: False) -> dict | None:
    """Point d'entrée du module : les doublons parmi les fichiers personnels relevés par stockage.scan().

    `progression(étape, fait, total)` : étape « rapide » (fichiers comparés par leur début et leur fin),
    puis « contenu » (octets lus en entier). Renvoie None si `arret()` devient vrai avant la fin.
    """
    debut = time.perf_counter()
    arbre = _Arbre(personnels)
    empreintes = _Empreintes(progression, arret)

    # 1. Candidats, sans rien lire : dossiers de même forme (mêmes noms, mêmes tailles), fichiers de même taille.
    formes = {d: (arbre.forme[d], arbre.total[d]) for d in arbre.ordre
              if arbre.complet[d] and arbre.total[d] >= TAILLE_MIN_DOSSIER}
    dossiers = _groupes(formes)
    contenus = {d: arbre.contenu(d) for groupe in dossiers for d in groupe}
    tailles = {os.path.join(dossier, nom): taille for dossier, liste in arbre.fichiers.items()
               for nom, taille in liste
               if taille >= TAILLE_MIN_FICHIER and os.path.splitext(nom)[1].lower() not in TECHNIQUES}
    fichiers = _groupes(tailles)
    tailles |= {chemin: taille for contenu in contenus.values() for _, chemin, taille in contenu}
    try:
        # 2. Comparaison rapide de tous les candidats : début et fin de chaque fichier.
        empreintes.calculer_rapides({c: tailles[c] for c in _a_lire(dossiers, fichiers, contenus)})
        dossiers = _par_signature(dossiers, contenus, empreintes.rapides)
        fichiers = _par_empreinte(fichiers, tailles, empreintes.rapides)
        # 3. Contenu complet de ceux qui se ressemblent encore, en une seule passe.
        empreintes.calculer_completes({c: tailles[c] for c in _a_lire(dossiers, fichiers, contenus)})
    except Arret:
        return None
    dossiers = _par_signature(dossiers, contenus, empreintes.completes)
    fichiers = [g for g in map(_sans_liens_physiques, _par_empreinte(fichiers, tailles, empreintes.completes))
                if len(g) > 1]

    # Seulement les dossiers du haut : les sous-dossiers de deux copies sont forcément en double aussi.
    tous = {d for groupe in dossiers for d in groupe}
    dossiers = [g for g in ([d for d in groupe if not arbre.dans(d, tous)] for groupe in dossiers) if len(g) > 1]
    # Les fichiers des dossiers en double sont déjà comptés avec leur dossier : on ne les remontre que
    # s'ils ont aussi une copie ailleurs, et seules les copies hors de ces dossiers sont « en trop ».
    dans_doublons = {d for groupe in dossiers for d in groupe}
    groupes = [{"dossier": True, "nom": os.path.basename(groupe[0]), "taille": arbre.total[groupe[0]],
                "copies": groupe, "en_trop": arbre.total[groupe[0]] * (len(groupe) - 1)} for groupe in dossiers]
    for groupe in fichiers:
        dehors = [chemin for chemin in groupe if not arbre.dans(chemin, dans_doublons)]
        if not dehors:
            continue
        taille = tailles[groupe[0]]
        en_trop = taille * (len(dehors) if len(dehors) < len(groupe) else len(groupe) - 1)
        groupes.append({"dossier": False, "nom": os.path.basename(groupe[0]), "taille": taille, "copies": groupe,
                        "en_trop": en_trop})
    groupes.sort(key=lambda g: g["en_trop"], reverse=True)
    return {
        "groupes": groupes[:NB_GROUPES],
        "nombre": len(groupes),
        "en_trop": sum(g["en_trop"] for g in groupes),
        "duree": time.perf_counter() - debut,
    }


def retirer(resultat: dict, chemin: str) -> None:
    """Met à jour les doublons trouvés après la suppression de `chemin` (fichier ou dossier).

    Une copie partie avec `chemin`, ou un dossier dont un fichier est parti (il n'est plus identique), ne
    compte plus ; un groupe qui n'a plus qu'un exemplaire n'est plus en double. Les groupes qui n'étaient
    pas montrés ne sont pas recalculés : « Relancer la recherche » le fait.
    """
    copies_de_dossiers = [copie for groupe in resultat["groupes"] if groupe["dossier"] for copie in groupe["copies"]]
    gardes = []
    for groupe in resultat["groupes"]:
        avant = groupe["en_trop"]
        parties = [copie for copie in groupe["copies"] if dans(copie, chemin) or dans(chemin, copie)]
        groupe["copies"] = [copie for copie in groupe["copies"] if copie not in parties]
        reste = len(groupe["copies"]) - 1  # exemplaires en trop, au plus
        if reste < 1:
            groupe["en_trop"] = 0
            resultat["nombre"] -= 1
        elif groupe["dossier"]:
            groupe["en_trop"] = groupe["taille"] * reste
        elif parties:
            # Seules les copies rangées hors des dossiers en double étaient comptées en trop.
            dehors = sum(1 for copie in parties if not any(dans(copie, d) for d in copies_de_dossiers))
            groupe["en_trop"] = max(0, min(avant - groupe["taille"] * dehors, groupe["taille"] * reste))
        if reste >= 1:
            gardes.append(groupe)
        resultat["en_trop"] -= avant - groupe["en_trop"]
    resultat["groupes"] = sorted(gardes, key=lambda g: g["en_trop"], reverse=True)
