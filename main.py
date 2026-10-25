"""Bilan santé PC : lance l'interface, ou le mode terminal avec `python main.py --cli`.

Après le clic sur « Mettre à jour », la nouvelle version est lancée en mode installation (voir modules/mise_a_jour.py).
"""

import sys

import historique
import journal
from modules import disque, mise_a_jour
from ui import analyse


def afficher_demarrage(resultat: dict) -> None:
    print("\nProgrammes lancés au démarrage :")
    for programme in resultat["programmes"]:
        print(f"\n- {programme['nom']}")
        print(f"    Chemin  : {programme['chemin']}")
        print(f"    Éditeur : {programme['editeur'] or 'inconnu'}")
        print(f"    Source  : {programme['source']}")


def afficher_disque(resultat: dict) -> None:
    print("\nPlus gros dossiers de ton profil :")
    for dossier in resultat["gros_dossiers"]:
        print(f"  {disque.taille_lisible(dossier['taille']):>10}  {dossier['chemin']}")


def afficher_ressources(resultat: dict) -> None:
    print("\nProgrammes qui occupent le plus de mémoire :")
    for programme in resultat["processus"]:
        print(f"  {disque.taille_lisible(programme['octets']):>10}  {programme['nom']}")


def cli() -> None:
    print("Analyse en cours, cela prend moins d'une minute...\n")
    resultat = analyse.analyser()
    print(analyse.rapport_texte(resultat))
    entrees = historique.enregistrer(resultat)
    if resultat["bilan"] and resultat["bilan"]["score"] is not None:
        print("\nDepuis la dernière fois :")
        print("\n".join(historique.comparer(entrees, analyse.NOMS)))
    modules = resultat["modules"]
    print("\n=== Détails ===")
    for cle, afficher in (("demarrage", afficher_demarrage), ("disque", afficher_disque),
                          ("ressources", afficher_ressources)):
        if modules.get(cle):
            afficher(modules[cle])


def main() -> int:
    journal.configurer()
    if "--cli" in sys.argv:
        cli()
        return 0
    if mise_a_jour.ARGUMENT_INSTALLER in sys.argv:
        return mise_a_jour.installer_depuis(sys.argv)
    from ui.fenetre import lancer_interface  # importé ici : le mode terminal se passe de PySide6
    return lancer_interface()


if __name__ == "__main__":
    sys.exit(main())
