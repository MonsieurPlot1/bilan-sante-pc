# Bilan santé PC

App Windows grand public : scanne le PC et explique en français clair pourquoi il rame. Score /100 + 3 conseils max.

## Règles
- LECTURE SEULE : l'app ne modifie, ne supprime, ne désactive rien sur le système.
- 100 % local : aucune donnée n'est envoyée ailleurs, aucun réseau.
- Un module = un fichier dans `modules/`, avec une fonction `scan()` qui renvoie un dict (score partiel + constats).
- La logique (modules/) est séparée de l'interface (ui/) : les modules doivent tourner sans PySide6.
- Textes affichés en français simple, sans jargon. Jamais "désactive X" sans préciser que certains programmes sont légitimes.

## Stack
Python 3.12, PySide6, psutil, winreg, PyInstaller. Windows 11, VS Code.

## v0.1
Modules démarrage et disque uniquement.

## Style
Code commenté en français, fonctions courtes, type hints, pas de dépendance inutile.