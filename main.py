"""Bilan santé PC : affiche le résultat des modules dans le terminal (pas encore d'interface)."""

from modules import demarrage


def main() -> None:
    resultat = demarrage.scan()
    for constat in resultat["constats"]:
        print(constat)
    for programme in resultat["programmes"]:
        print(f"\n- {programme['nom']}")
        print(f"    Chemin  : {programme['chemin']}")
        print(f"    Éditeur : {programme['editeur'] or 'inconnu'}")
        print(f"    Source  : {programme['source']}")


if __name__ == "__main__":
    main()
