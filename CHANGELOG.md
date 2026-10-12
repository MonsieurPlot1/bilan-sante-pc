# Journal des versions

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
