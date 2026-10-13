# Journal des versions

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
