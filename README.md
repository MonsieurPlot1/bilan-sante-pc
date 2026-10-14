# Bilan santé PC

Une application Windows qui scanne ton PC et t'explique en français clair pourquoi il rame :
un score sur 100 et 3 conseils au maximum.

## Ce qu'elle lit

- **Démarrage** : les programmes lancés avec Windows (registre `Run` et dossiers Démarrage), sans
  compter ceux désactivés dans Paramètres > Applications > Démarrage.
- **Disque** : l'espace libre de chaque disque et les plus gros dossiers de ton profil utilisateur,
  et si Windows est sur un SSD ou sur un disque dur classique (HDD, conseil hors score).
- **Fichiers inutiles** (hors score) : la taille de la Corbeille, des fichiers temporaires et du cache
  des navigateurs (Chrome, Edge, Firefox). Un conseil
  n'apparaît que si les vider ferait vraiment de la place sur un disque presque plein. Un bouton
  permet de vider la Corbeille, après confirmation.
- **Mémoire et processeur** : la mémoire vive utilisée, la charge du processeur mesurée pendant
  3 secondes, les 5 programmes qui prennent le plus de mémoire et la mémoire vive installée
  (conseil hors score sous 8 Go).
- **Redémarrage** : depuis combien de jours Windows n'a pas vraiment redémarré (« Arrêter » ne
  suffit pas, à cause du démarrage rapide), et si une mise à jour attend un redémarrage.
- **Alimentation** (hors score) : si Windows bride le PC pour économiser l'énergie (économiseur
  d'énergie, mode « Meilleure efficacité énergétique » ou « Économies d'énergie »), avec où le changer.
- **Batterie** (PC portables seulement) : le niveau de charge, le branchement et l'usure, lue auprès
  du pilote de batterie de Windows. Si le PC ne donne pas cette information, l'application l'écrit
  au lieu d'inventer un chiffre.

## Ce qu'elle ne fait jamais

- Elle ne modifie, ne supprime et ne désactive rien : elle se contente de lire.
  Seule exception : le bouton « Vider la Corbeille », qui n'agit que si tu cliques dessus
  et que tu confirmes dans la fenêtre de Windows. Pense à vérifier la Corbeille avant : c'est définitif.
- Elle n'envoie aucune donnée : tout reste sur ton PC, sans aucun accès au réseau.

Elle écrit seulement dans `%LOCALAPPDATA%\BilanSantePC` :
- `bilan.log` : un journal, utile en cas de problème ;
- `historique.json` : les chiffres de chaque analyse (date, scores, espace disque utilisé), pour
  l'encadré « Depuis la dernière fois » et le graphique. Aucun nom de programme ni de fichier.
  Le bouton « Effacer l'historique » le supprime.

Le bouton « Enregistrer le rapport » crée une page HTML, uniquement à l'endroit que tu choisis.
Ton dossier personnel y apparaît sous la forme `%USERPROFILE%`, sans ton nom d'utilisateur.

## Le score

Le score sur 100 additionne les points de chaque partie : Démarrage 25, Disque 25,
Mémoire et processeur 20, Redémarrage 15, Batterie 15. Sans batterie, ou si son usure n'est pas
mesurable, ses points vont aux autres parties (30, 30, 25 et 15). Tous les seuils sont dans `config.py`.
Les scores d'une version du calcul ne se comparent pas avec ceux d'une autre (calcul v4 depuis
que les programmes désactivés au démarrage ne comptent plus).

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
