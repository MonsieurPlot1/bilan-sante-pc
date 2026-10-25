"""Réglages de l'application : version et seuils du barème."""

VERSION = "0.4.0"

# Version du calcul du score : les scores de versions différentes ne se comparent pas.
SCORE_VERSION = 4

# Points de chaque module (total 100). Sans batterie, ou si son usure n'est pas mesurable,
# ses points sont répartis sur les autres modules.
POINTS_AVEC_BATTERIE = {"demarrage": 25, "disque": 25, "ressources": 20, "redemarrage": 15, "batterie": 15}
POINTS_SANS_BATTERIE = {"demarrage": 30, "disque": 30, "ressources": 25, "redemarrage": 15}

# Chaque mesure garde tous ses points jusqu'au seuil OK, puis en perd régulièrement
# jusqu'au seuil ZÉRO, où elle n'en a plus aucun.

# Disque système (C:) : % de remplissage.
DISQUE_SEUIL_OK = 70
DISQUE_SEUIL_ZERO = 95

# Démarrage : nombre de programmes lancés avec Windows.
DEMARRAGE_NB_OK = 10
DEMARRAGE_NB_ZERO = 27

# Ressources : moyenne de la mémoire vive (% utilisé) et du processeur (% occupé).
RAM_SEUIL_OK = 70
RAM_SEUIL_ZERO = 95
CPU_SEUIL_OK = 50
CPU_SEUIL_ZERO = 95

# Redémarrage : jours depuis le dernier redémarrage complet.
REDEMARRAGE_JOURS_OK = 7
REDEMARRAGE_JOURS_ZERO = 30
# Mise à jour en attente d'un redémarrage : la partie garde au plus cette part de ses points.
REDEMARRAGE_EN_ATTENTE_MAX = 0.5

# Batterie : usure en % de la capacité d'origine perdue.
BATTERIE_USURE_OK = 20
BATTERIE_USURE_ZERO = 60

# Mode d'alimentation (hors score) : place de son conseil parmi les autres, en points « regagnés ».
# Un PC bridé est plus lent en tout, et se règle en quelques clics.
ALIMENTATION_IMPACT = 10

# Windows sur un disque dur classique (HDD, hors score) : poids de son conseil, le plus fort des conseils
# hors score, car c'est souvent la première cause de lenteur.
DISQUE_DUR_IMPACT = 15

# Mémoire vive installée (hors score) : conseil en dessous de ce minimum, avec ce poids parmi les conseils
# (moins que l'alimentation : en ajouter coûte de l'argent).
RAM_INSTALLEE_MIN = 8 * 1024**3
RAM_INSTALLEE_IMPACT = 8

# Jeux et affichage (hors score) : poids des conseils parmi les autres.
# Écran utilisé nettement sous sa fréquence maximale : toute l'image est moins fluide (souris, défilement, jeux),
# et ça se règle en deux clics. Conseil si la fréquence utilisée est sous cette part du maximum (60 Hz sur un
# écran 75 Hz : oui ; 144 Hz sur un écran 165 Hz : non).
ECRAN_FREQUENCE_IMPACT = 9
ECRAN_FREQUENCE_PART_MIN = 0.85
# Pilote de la carte des jeux plus vieux que ça (en jours) : moins de performances et plus de bugs dans les jeux
# récents.
PILOTE_GRAPHIQUE_AGE_MAX = 180
PILOTE_GRAPHIQUE_IMPACT = 5
# Mode jeu de Windows coupé : effet plus modeste, et seulement pendant une partie.
MODE_JEU_IMPACT = 3

# Conseils.
NB_CONSEILS_MAX = 3
GROS_DOSSIER_SEUIL = 5 * 1024**3  # un dossier personnel est signalé à partir de 5 Go
