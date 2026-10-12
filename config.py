"""Réglages de l'application : version et seuils du barème."""

VERSION = "0.1.0"

# Version du calcul du score : les scores de versions différentes ne se comparent pas.
SCORE_VERSION = 2

# Points de chaque module (total 100). Sans batterie, ou si son usure n'est pas mesurable,
# ses points sont répartis sur les autres modules.
POINTS_AVEC_BATTERIE = {"demarrage": 30, "disque": 30, "ressources": 25, "batterie": 15}
POINTS_SANS_BATTERIE = {"demarrage": 35, "disque": 35, "ressources": 30}

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

# Batterie : usure en % de la capacité d'origine perdue.
BATTERIE_USURE_OK = 20
BATTERIE_USURE_ZERO = 60

# Conseils.
NB_CONSEILS_MAX = 3
GROS_DOSSIER_SEUIL = 5 * 1024**3  # un dossier personnel est signalé à partir de 5 Go
