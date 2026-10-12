"""Réglages de l'application : version et seuils du barème."""

VERSION = "0.1.0"

# Disque système (C:) : 50 points.
POINTS_DISQUE = 50
DISQUE_SEUIL_OK = 70     # % de remplissage jusqu'auquel le disque garde tous ses points
DISQUE_SEUIL_ZERO = 95   # % de remplissage à partir duquel le disque n'a plus aucun point

# Programmes au démarrage : 50 points.
POINTS_DEMARRAGE = 50
DEMARRAGE_NB_OK = 10     # nombre de programmes sans pénalité
DEMARRAGE_PENALITE = 3   # points retirés par programme au-delà

# Conseils.
NB_CONSEILS_MAX = 3
GROS_DOSSIER_SEUIL = 5 * 1024**3  # un dossier personnel est signalé à partir de 5 Go
