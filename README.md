# Bilan santé PC

Une application Windows qui scanne ton PC et t'explique en français clair pourquoi il rame :
un score sur 100 et 3 conseils au maximum.

## Ce qu'elle lit

- **Démarrage** : les programmes lancés avec Windows (registre `Run` et dossiers Démarrage), sans
  compter ceux désactivés dans Paramètres > Applications > Démarrage.
- **Disque** : l'espace libre de chaque disque et les plus gros dossiers de ton profil utilisateur,
  et si Windows est sur un SSD ou sur un disque dur classique (HDD, conseil hors score).
- **Fichiers inutiles** (hors score) : la taille de la Corbeille, des fichiers temporaires, du cache
  des navigateurs (Chrome, Edge, Firefox) et de l'ancienne version de Windows gardée après une grosse
  mise à jour (`Windows.old`, taille approximative). Un conseil
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

## L'onglet Stockage

Il montre ce qui prend de la place sur un disque : les plus gros dossiers et fichiers, et 12 catégories
(Système, Applications, Jeux, Vidéos, Photos, Musique, Documents, Archives, Fichiers temporaires, Corbeille,
Sauvegardes, Autres). Un fichier est classé d'abord selon son emplacement (une vidéo dans le dossier d'un jeu
compte dans Jeux), puis selon son extension. Système, c'est l'espace utilisé moins tout le reste : Windows et
les fichiers que l'application n'a pas le droit de lire. L'analyse parcourt tout le disque (une ou deux
minutes), elle n'est pas enregistrée et n'entre pas dans le score.

Ensuite, « Chercher les doublons » compare le contenu de tes fichiers personnels (pas ceux de Windows, des
logiciels ni des jeux, où des copies sont normales) et montre les fichiers et les dossiers en double d'au
moins 1 Mo, avec la place qu'ils prennent en trop. Deux fichiers sont en double s'ils ont exactement le
même contenu, même avec des noms différents. La recherche lit les fichiers sans rien modifier.

À côté de chaque dossier et fichier trouvé (jeux, logiciels, caches, vidéos, archives… et les copies en
double), un bouton « Supprimer » l'efface définitivement, après confirmation : il ne passe pas par la
Corbeille, la place est libérée tout de suite mais il n'est plus récupérable. La confirmation donne la
taille réelle et le nombre de fichiers. Pour un jeu ou un logiciel, la désinstallation (Paramètres ou son
lanceur) reste plus propre. Le bouton n'apparaît jamais sur ce qui casserait Windows : le dossier Windows,
l'ancien Windows (Windows.old), les dossiers de Windows et de Microsoft dans Program Files, ProgramData ou
AppData, le dossier des fichiers temporaires, ni ton dossier personnel, Bureau, Documents ou
Téléchargements eux-mêmes.

## Ce qu'elle ne fait jamais

- Elle ne modifie, ne supprime et ne désactive rien : elle se contente de lire.
  Deux exceptions, qui n'agissent que si tu cliques dessus et que tu confirmes :
  - le bouton « Vider la Corbeille » (confirmation dans la fenêtre de Windows). Pense à vérifier
    la Corbeille avant : c'est définitif ;
  - les boutons « Supprimer » de l'onglet Stockage, qui effacent définitivement un fichier ou un
    dossier, sans passer par la Corbeille : vérifie avec « Afficher » avant de confirmer.
- Les boutons « Ouvrir » sous les conseils affichent seulement la bonne page des Paramètres, le dossier
  concerné ou le Gestionnaire des tâches : c'est toi qui décides ensuite quoi changer. Dans l'onglet
  Stockage, « Afficher » ouvre seulement l'Explorateur à l'emplacement d'un dossier ou d'un fichier.
- Elle n'envoie aucune donnée : tout reste sur ton PC, sans aucun accès au réseau.

Elle écrit seulement dans `%LOCALAPPDATA%\BilanSantePC` :
- `bilan.log` : un journal, utile en cas de problème ;
- `historique.json` : les chiffres de chaque analyse (date, scores, espace disque utilisé), pour
  l'encadré « Depuis la dernière fois » (avec l'évolution du disque sur le dernier mois) et le graphique. Aucun nom de programme ni de fichier.
  Le bouton « Effacer l'historique » le supprime.
- `reglages.json` : le mode clair ou sombre choisi avec le bouton en haut de la fenêtre (sans ce
  fichier, l'application suit le mode de Windows).

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
`dist\BilanSantePC` pour l'emporter sur un autre PC. L'icône vient de `assets\icon.ico`
(ses sources : `icon.svg`, et `icon-simple.svg` pour les petites tailles, de 16 à 24 pixels).

La police de l'interface est Inter (`assets\polices\InterVariable.ttf`), de The Inter Project Authors, sous
licence SIL Open Font License 1.1 (`assets\polices\OFL.txt`) : elle est livrée avec l'application, rien n'est
installé dans Windows. Si elle manque, l'interface utilise Segoe UI Variable.
