"""Réglages de l'application : version et seuils du barème."""

VERSION = "0.1.9"

# Version du calcul du score : les scores de versions différentes ne se comparent pas.
SCORE_VERSION = 3

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

# Conseils.
NB_CONSEILS_MAX = 3
GROS_DOSSIER_SEUIL = 5 * 1024**3  # un dossier personnel est signalé à partir de 5 Go
