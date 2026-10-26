# Bilan santé PC

App Windows grand public : scanne le PC et explique en français clair pourquoi il rame. Score /100 + 3 conseils max.

## Règles
- LECTURE SEULE : l'app ne modifie, ne supprime, ne désactive rien sur le système.
  Seules exceptions, uniquement sur clic : le bouton « Vider la Corbeille » (module fichiers), avec la
  confirmation de Windows, et les boutons « Supprimer » de l'onglet Stockage, qui suppriment définitivement
  (sans passer par la Corbeille, à ma demande) un fichier ou un dossier de l'analyse après confirmation, jeux
  et logiciels compris ; jamais Windows, les dossiers de Windows et de Microsoft, les emplacements des
  logiciels, le dossier temporaire ni le profil et ses dossiers (`stockage.supprimable`). Et, à ma demande, le
  bouton « Mettre à jour » (`modules/mise_a_jour.py`), qui après confirmation lance l'installateur de la nouvelle
  version : il remplace seulement les fichiers de l'application elle-même (son .exe et `_internal`, l'ancienne
  version remise en place en cas d'échec).
  Aucune autre action ne s'ajoute sans mon accord explicite.
  Les boutons « Ouvrir » des conseils ne font qu'ouvrir une page des Paramètres, un dossier ou un outil de Windows.
- 100 % local : aucune donnée n'est envoyée ailleurs, aucun réseau. Deux exceptions, à ma demande : le test de
  l'onglet Connexion (`modules/connexion.py`), uniquement sur clic, qui échange des données de test tirées au
  hasard avec les serveurs de Cloudflare (speed.cloudflare.com) ; et les mises à jour (`modules/mise_a_jour.py`) :
  à l'ouverture, une requête à GitHub pour la liste des versions publiées (seulement le nom et la version de
  l'appli), puis, sur clic, le téléchargement de l'installateur depuis GitHub. Rien sur le PC ni sur l'utilisateur ne part,
  et aucun autre accès au réseau ne s'ajoute sans mon accord explicite.
- Un module = un fichier dans `modules/`, avec une fonction `scan()` qui renvoie un dict (mesures + constats ; le score est calculé dans `modules/score.py`).
- La logique (modules/) est séparée de l'interface (ui/) : les modules doivent tourner sans PySide6.
- Textes affichés en français simple, sans jargon. Jamais "désactive X" sans préciser que certains programmes sont légitimes.

## Stack
Python 3.15, PySide6, psutil, winreg, PyInstaller. Windows 11, VS Code.
Interface dans l'esprit Apple (verre dépoli sur une lueur douce) : matières dans `ui/verre.py`, composants dans
`ui/widgets.py`, couleurs et échelle typographique dans `ui/theme.py` (police Segoe UI Variable : Inter, essayée,
était moins nette et plus lente à dessiner). Les pages restent opaques (elles peignent la lueur) : c'est ce qui
rend le défilement fluide, ne pas leur donner de `background` dans la feuille de style (test
`test_pages_opaques_pour_un_defilement_fluide`). Pour la même raison, rien ne doit recouvrir une page : la barre
du haut en verre est posée au-dessus et peint elle-même, floutée, la bande de page passée dessous.
Infobulles : seulement pour un bouton à icône seule, un terme technique ou une info visible nulle part ailleurs
(jamais pour répéter un texte affiché, sauf s'il est coupé). `setToolTip` suffit : `Infobulle` (ui/widgets.py) les
affiche toutes dans le style de l'application, jamais la bulle grise de Qt.

## Modules
- Dans le score : démarrage, disque, ressources (mémoire et processeur), redémarrage, batterie (PC portables).
- Hors score : fichiers (Corbeille, fichiers temporaires, cache des navigateurs, Windows.old), alimentation (mode d'économie d'énergie), jeux (fréquence des écrans, pilote de la carte graphique des jeux, Mode jeu).
- Onglet à part, hors du bilan : stockage (`modules/stockage.py`, page `ui/stockage.py`), ce qui occupe un disque en 12 catégories, et doublons (`modules/doublons.py`), fichiers et dossiers personnels au contenu identique.
- Onglet à part, hors du bilan : connexion (`modules/connexion.py`, page `ui/connexion.py`), la liaison avec la box (lue auprès de Windows) et le test de débit sur clic. Les tests n'utilisent jamais le réseau (fixture `reseau_interdit`).
- Hors du bilan : mises à jour (`modules/mise_a_jour.py`, bouton « Mettre à jour » de la barre du haut).
  L'installateur téléchargé (Inno Setup, `installateur.iss`), lancé sans questions avec `/ATTENDRE=<pid>`, remplace
  l'application une fois celle-ci fermée, puis la rouvre. L'ancien mode `--installer` (les versions jusqu'à la
  v0.4.1 installent un zip avec) ne reste que pour la première version publiée avec un installateur. Les tests
  n'utilisent jamais le réseau et ne lancent rien (fixture `reseau_et_lancement_interdits`).
- Barème et seuils dans `config.py`, calcul du score et conseils dans `modules/score.py`.

## Style
Code commenté en français, fonctions courtes, type hints, pas de dépendance inutile.

## Workflow
- Avant de dire qu'une tâche est terminée : lance les tests, relis ton propre diff, corrige les problèmes trouvés.
- Utilise les skills de review/tests disponibles quand ils s'appliquent.
- Ne réécris pas du code qui fonctionne et qui est testé.
- Si tu es bloqué après 3 tentatives sur le même problème, arrête-toi et explique où ça coince.
- Un commit git par tâche terminée. Pas de `git push` sans mon accord (voir « Versions et tags »).
- Si le dossier graphify-out/ existe, lance `graphify update .` après avoir modifié du code, pour que le graphe ne soit pas périmé. S'il n'existe pas, ne le crée pas.

## Environnement de dev (hors git)
- Python 3.15 seul installé. Visual Studio Build Tools 2026 (C++) installés : nécessaires pour compiler `tree-sitter` (pas de wheel 3.15).
- Inno Setup 6, installé pour l'utilisateur (`winget install JRSoftware.InnoSetup --scope user`) : `build.bat` fabrique l'installateur avec.
- graphify : `pip install --user graphifyy`. Pas dans le PATH → utiliser `& "$env:APPDATA\Python\Python315\Scripts\graphify.exe"`.
- Hooks git graphify (post-commit, post-checkout, merge driver) dans `.git/hooks`, non versionnés : après un clone, relancer `graphify hook install`.
- `graphify-out/` est ignoré par git (chemins propres à la machine).
- Skills addyosmani/agent-skills dans `.agents/skills/` (versionnés, verrouillés par `skills-lock.json`). `.claude/skills/` = jonctions Windows, ignorées : les recréer avec `npx skills experimental_install`.
- Plugin ponytail activé via `.claude/settings.json`. Skill graphify installé globalement (`~/.claude/skills/graphify`).

## Versions et tags
- Format des versions : vMAJEURE.MINEURE.CORRECTIF (ex. v0.1.1). Tant que l'app est en phase de test on reste en v0.x.x.
  - CORRECTIF (v0.1.0 → v0.1.1) : bug corrigé, petit ajustement visuel ou de texte.
  - MINEURE (v0.1.x → v0.2.0) : nouvelle fonctionnalité ou nouveau module.
  - MAJEURE (v0.x → v1.0.0) : seulement quand je le décide.
- Après chaque série de modifications terminée et testée, fais un commit avec un message clair, puis PROPOSE un tag. Ne crée JAMAIS un tag sans me l'avoir demandé.
- Quand tu proposes un tag : indique la dernière version existante (git tag --sort=-v:refname), explique en une phrase ce qui a changé, suggère la version adaptée (CORRECTIF ou MINEURE) et demande-moi de choisir : la version suggérée, une autre version que je tape, ou pas de tag pour cette fois.
- Une fois le tag validé, dans cet ordre : mets à jour VERSION dans config.py, ajoute l'entrée correspondante dans CHANGELOG.md, fais un commit "Version vX.Y.Z", crée le tag annoté avec git tag -a vX.Y.Z -F <fichier>. Le message du tag = une ligne de titre « vX.Y.Z : résumé en une phrase », une ligne vide, puis le contenu de l'entrée vX.Y.Z du CHANGELOG (ce qui a changé).
- Ne fais PAS de git push (ni du code ni des tags) sans que je te le demande explicitement. Quand je le demande, le tag se pousse avec git push origin vX.Y.Z.
- Juste après avoir poussé un tag, crée sa release GitHub : gh release create vX.Y.Z --title "vX.Y.Z" --notes-file <entrée vX.Y.Z du CHANGELOG> --verify-tag, avec --prerelease tant qu'on est en v0.x. Toujours avec l'installateur en pièce jointe (les mises à jour de l'appli le téléchargent et le lancent) : `dist\BilanSantePC-Installation-vX.Y.Z.exe`, fait par `build.bat` après le commit de version. Vérifie avant que l'application qu'il installe démarre et que son journal donne la bonne version. Plus de zip, à ma demande, sauf pour la première version publiée avec un installateur : son zip `BilanSantePC-vX.Y.Z-windows.zip` (dossier `BilanSantePC` à sa racine) permet aux versions jusqu'à la v0.4.1 de s'y mettre à jour.
- Si un tag existe déjà ou si la version est plus basse que la dernière, préviens-moi au lieu de continuer.
