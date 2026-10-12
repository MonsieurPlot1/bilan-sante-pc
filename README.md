# Bilan santé PC

Une application Windows qui scanne ton PC et t'explique en français clair pourquoi il rame :
un score sur 100 et 3 conseils au maximum.

## Ce qu'elle lit

- **Démarrage** : les programmes lancés avec Windows (registre `Run` et dossiers Démarrage).
- **Disque** : l'espace libre de chaque disque et les plus gros dossiers de ton profil utilisateur.

## Ce qu'elle ne fait jamais

- Elle ne modifie, ne supprime et ne désactive rien : elle se contente de lire.
- Elle n'envoie aucune donnée : tout reste sur ton PC, sans aucun accès au réseau.

Le seul fichier écrit est un journal local, utile en cas de problème :
`%LOCALAPPDATA%\BilanSantePC\bilan.log`.

## Lancer en mode développement

Python 3.15 sous Windows 11.

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py           # interface
python main.py --cli     # résultat dans le terminal
python -m pytest         # tests
```

## Compiler le .exe

```
build.bat
```

Le résultat est dans `dist\BilanSantePC\BilanSantePC.exe` : copie tout le dossier
`dist\BilanSantePC` pour l'emporter sur un autre PC. Pour une icône, place un fichier
`assets\icon.ico` avant de compiler.
