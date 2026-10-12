# Bilan santé PC

App Windows grand public : scanne le PC et explique en français clair pourquoi il rame. Score /100 + 3 conseils max.

## Règles
- LECTURE SEULE : l'app ne modifie, ne supprime, ne désactive rien sur le système.
- 100 % local : aucune donnée n'est envoyée ailleurs, aucun réseau.
- Un module = un fichier dans `modules/`, avec une fonction `scan()` qui renvoie un dict (score partiel + constats).
- La logique (modules/) est séparée de l'interface (ui/) : les modules doivent tourner sans PySide6.
- Textes affichés en français simple, sans jargon. Jamais "désactive X" sans préciser que certains programmes sont légitimes.

## Stack
Python 3.15, PySide6, psutil, winreg, PyInstaller. Windows 11, VS Code.

## v0.1
Modules démarrage et disque uniquement.

## Style
Code commenté en français, fonctions courtes, type hints, pas de dépendance inutile.

## Workflow
- Avant de dire qu'une tâche est terminée : lance les tests, relis ton propre diff, corrige les problèmes trouvés.
- Utilise les skills de review/tests disponibles quand ils s'appliquent.
- Ne réécris pas du code qui fonctionne et qui est testé.
- Si tu es bloqué après 3 tentatives sur le même problème, arrête-toi et explique où ça coince.
- Un commit git par tâche terminée.
- Si le dossier graphify-out/ existe, lance `graphify update .` après avoir modifié du code, pour que le graphe ne soit pas périmé. S'il n'existe pas, ne le crée pas.

## Environnement de dev (hors git)
- Python 3.15 seul installé. Visual Studio Build Tools 2026 (C++) installés : nécessaires pour compiler `tree-sitter` (pas de wheel 3.15).
- graphify : `pip install --user graphifyy`. Pas dans le PATH → utiliser `& "$env:APPDATA\Python\Python315\Scripts\graphify.exe"`.
- Hooks git graphify (post-commit, post-checkout, merge driver) dans `.git/hooks`, non versionnés : après un clone, relancer `graphify hook install`.
- `graphify-out/` est ignoré par git (chemins propres à la machine).
- Skills addyosmani/agent-skills dans `.agents/skills/` (versionnés, verrouillés par `skills-lock.json`). `.claude/skills/` = jonctions Windows, ignorées : les recréer avec `npx skills experimental_install`.
- Plugin ponytail activé via `.claude/settings.json`. Skill graphify installé globalement (`~/.claude/skills/graphify`).