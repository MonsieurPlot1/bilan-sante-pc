# Bilan santé PC

Une application Windows qui scanne ton PC et t'explique en français clair pourquoi il rame :
un score sur 100 et 3 conseils au maximum.

## Ce qu'elle lit

- **Démarrage** : les programmes lancés avec Windows (registre `Run` et dossiers Démarrage).
- **Disque** : l'espace libre de chaque disque et les plus gros dossiers de ton profil utilisateur.
- **Mémoire et processeur** : la mémoire vive utilisée, la charge du processeur mesurée pendant
  3 secondes et les 5 programmes qui prennent le plus de mémoire.
- **Batterie** (PC portables seulement) : le niveau de charge, le branchement et l'usure, lue auprès
  du pilote de batterie de Windows. Si le PC ne donne pas cette information, l'application l'écrit
  au lieu d'inventer un chiffre.

## Ce qu'elle ne fait jamais

- Elle ne modifie, ne supprime et ne désactive rien : elle se contente de lire.
- Elle n'envoie aucune donnée : tout reste sur ton PC, sans aucun accès au réseau.

Elle écrit seulement dans `%LOCALAPPDATA%\BilanSantePC` :
- `bilan.log` : un journal, utile en cas de problème ;
- `historique.json` : les chiffres de chaque analyse (date, scores, espace disque utilisé), pour
  l'encadré « Depuis la dernière fois » et le graphique. Aucun nom de programme ni de fichier.
  Le bouton « Effacer l'historique » le supprime.

Le bouton « Enregistrer le rapport » crée une page HTML, uniquement à l'endroit que tu choisis.
Ton dossier personnel y apparaît sous la forme `%USERPROFILE%`, sans ton nom d'utilisateur.

## Le score

Le score sur 100 additionne les points de chaque partie : Démarrage 30, Disque 30,
Mémoire et processeur 25, Batterie 15. Sans batterie, ou si son usure n'est pas mesurable, ses
points vont aux autres parties (35, 35 et 30). Tous les seuils sont dans `config.py`.
Les scores de la v0.1 (calcul v1) ne se comparent pas avec ceux d'aujourd'hui (calcul v2).

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
