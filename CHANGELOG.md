# Journal des versions

## v0.1.3 - 2026-10-12

- Nouveau module Mémoire et processeur : mémoire vive utilisée, charge du processeur
  et programmes les plus gourmands.
- Nouveau module Batterie (PC portables) : niveau, branchement et usure réelle lue auprès
  de Windows ; « Usure non mesurable sur ce PC » quand l'information n'existe pas.
- Score v2 : barème rééquilibré sur 4 parties, points de la batterie répartis sur les autres
  quand elle est absente. Les scores v1 ne sont pas comparables.
- Historique des analyses : encadré « Depuis la dernière fois », graphique des 20 derniers
  scores et bouton « Effacer l'historique ». Seulement des chiffres, enregistrés sur le PC.
- Bouton « Enregistrer le rapport » : page HTML autonome, sans nom d'utilisateur.

## v0.1.0 - 2026-10-12

Première version installable.

- Module Démarrage : liste les programmes lancés avec Windows, avec leur éditeur.
- Module Disque : espace libre des disques et plus gros dossiers du profil.
- Score sur 100 et 3 conseils au maximum, classés par utilité.
- Interface PySide6 en thème sombre : score coloré, détail par module, conseils,
  bouton « Copier le rapport ». L'analyse tourne en arrière-plan sans figer la fenêtre.
- Mode terminal : `python main.py --cli`.
- Journal local dans `%LOCALAPPDATA%\BilanSantePC`.
- Fabrication du .exe avec `build.bat` (PyInstaller).
