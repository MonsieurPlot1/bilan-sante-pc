# Journal des versions

## v0.2.6 - 2026-10-16

- Fichiers inutiles : l'ancienne version de Windows gardée après une grosse mise à jour (dossier
  Windows.old) est mesurée, avec une taille approximative, et comptée dans la place récupérable. Le
  conseil indique où la supprimer et prévient qu'on ne pourra plus revenir à l'ancienne version.

## v0.2.5 - 2026-10-14

- Démarrage : les programmes désactivés dans Paramètres > Applications > Démarrage ne comptent plus.
  Calcul du score v4 : les scores d'avant ne se comparent pas.
- Nouvelles vérifications (hors score) : Windows sur un SSD ou un disque dur classique, mémoire vive
  installée (conseil sous 8 Go) et cache des navigateurs (Chrome, Edge, Firefox) dans Fichiers inutiles.
- « Depuis la dernière fois » montre l'évolution du disque sur le dernier mois.
- Conseils juste sous le score, avec un bouton « Ouvrir » vers la bonne page des Paramètres, le dossier
  ou le Gestionnaire des tâches (ça ouvre seulement, rien n'est modifié).
- Thème clair : l'application suit Windows, et un bouton permet de choisir le mode clair ou sombre
  (choix retenu). Passage de l'un à l'autre en fondu, barre de titre comprise.
- Animations : jauge et barres qui se remplissent, progression qui glisse, conseils en fondu, détail
  qui se déplie, courbe qui se dessine, défilement doux. « Copier le rapport » confirme d'une coche.
- Tableaux du détail plus lisibles : longs chemins coupés au milieu, texte complet au survol.

## v0.2.0 - 2026-10-14

- Nouveau module Alimentation (hors score) : signale quand Windows bride le PC pour économiser
  l'énergie (économiseur d'énergie, mode « Meilleure efficacité énergétique » ou « Économies
  d'énergie ») et indique où le changer. Le score reste en calcul v3 : l'historique reste comparable.
- Pendant l'analyse, la fenêtre affiche la partie en cours (« Disque (2 sur 7) ») et une barre qui
  avance, au lieu d'une barre qui tourne sans fin.
- Les conseils tutoient, comme le reste de l'application.

## v0.1.10 - 2026-10-14

- Après « Vider la Corbeille », la fenêtre ne se fige plus : seule la Corbeille est remesurée,
  la taille des fichiers temporaires est reprise de l'analyse.

## v0.1.9 - 2026-10-13

- Bouton « Vider la Corbeille » dans la carte Fichiers inutiles : seule action de l'application qui
  modifie le PC, uniquement sur clic et après la confirmation de Windows. Si la confirmation est
  refusée, rien n'est supprimé. Le bouton est grisé quand la Corbeille est vide.
- Textes rassurants mis à jour : « L'application ne modifie rien sans ton accord ».

## v0.1.8 - 2026-10-13

- Nouveau module Fichiers inutiles (hors score) : taille de la Corbeille et des fichiers temporaires.
  Le conseil (vérifier puis vider la Corbeille, fichiers temporaires via Paramètres) n'apparaît que
  si libérer cette place aide vraiment un disque presque plein.
- Les cartes sans note (hors score ou en erreur) n'affichent plus de barre vide qui ferait croire à un 0.

## v0.1.7 - 2026-10-13

- Nouveau module Redémarrage : nombre de jours depuis le dernier vrai redémarrage (« Arrêter » ne
  suffit pas, à cause du démarrage rapide de Windows) et mise à jour de Windows en attente d'un
  redémarrage. Conseil : Démarrer > Marche/Arrêt > Redémarrer.
- Score v3 : Démarrage 25, Disque 25, Mémoire et processeur 20, Redémarrage 15, Batterie 15
  (sans batterie : 30, 30, 25 et 15). Les scores v2 ne sont pas comparables.

## v0.1.6 - 2026-10-13

Application plus légère, sans changement de fonctionnement.

- Mémoire vive de la fenêtre : environ 130 Mo -> 81 Mo (les polices de Windows ne sont plus
  toutes chargées pour rien).
- Liste des programmes gourmands lue en une seule fois : 1 s de processeur -> 0,02 s.
- L'analyse tourne en arrière-plan (priorité basse) : elle ne ralentit plus ce que tu fais pendant ce temps.
- Icônes gardées en mémoire : défilement de la fenêtre un peu plus léger.

## v0.1.5 - 2026-10-12

Refonte complète de l'interface, sans changement de fonctionnement.

- Thème sombre retravaillé, polices et icônes de Windows 11 (Segoe UI Variable, Segoe Fluent Icons).
- Score affiché dans une jauge circulaire animée, avec un état en toutes lettres
  (« Bon état », « À surveiller », « À améliorer »).
- Cartes par partie avec icône, score en pastille colorée, barre de progression et détail en tableau.
- Conseils présentés en cartes numérotées ; graphique de l'historique redessiné.
- Barre de titre Windows sombre.

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
