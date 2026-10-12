"""Bilan santé PC : affiche le résultat des modules dans le terminal (pas encore d'interface)."""

from modules import demarrage, disque


def afficher_demarrage() -> None:
    resultat = demarrage.scan()
    for constat in resultat["constats"]:
        print(constat)
    for programme in resultat["programmes"]:
        print(f"\n- {programme['nom']}")
        print(f"    Chemin  : {programme['chemin']}")
        print(f"    Éditeur : {programme['editeur'] or 'inconnu'}")
        print(f"    Source  : {programme['source']}")


def afficher_disque() -> None:
    print("Analyse des dossiers en cours, cela peut prendre une minute...")
    resultat = disque.scan()
    for constat in resultat["constats"]:
        print(constat)
    print("\nPlus gros dossiers de votre profil :")
    for dossier in resultat["gros_dossiers"]:
        print(f"  {disque.taille_lisible(dossier['taille']):>10}  {dossier['chemin']}")


def main() -> None:
    print("=== Démarrage ===")
    afficher_demarrage()
    print("\n=== Disque ===")
    afficher_disque()


if __name__ == "__main__":
    main()
