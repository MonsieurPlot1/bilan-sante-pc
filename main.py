"""Bilan santé PC : affiche le résultat des modules dans le terminal (pas encore d'interface)."""

import config
from modules import demarrage, disque, score


def afficher_demarrage(resultat: dict) -> None:
    for constat in resultat["constats"]:
        print(constat)
    for programme in resultat["programmes"]:
        print(f"\n- {programme['nom']}")
        print(f"    Chemin  : {programme['chemin']}")
        print(f"    Éditeur : {programme['editeur'] or 'inconnu'}")
        print(f"    Source  : {programme['source']}")


def afficher_disque(resultat: dict) -> None:
    for constat in resultat["constats"]:
        print(constat)
    print("\nPlus gros dossiers de votre profil :")
    for dossier in resultat["gros_dossiers"]:
        print(f"  {disque.taille_lisible(dossier['taille']):>10}  {dossier['chemin']}")


def afficher_score(resultat: dict) -> None:
    print(f"Score de santé : {resultat['score']} / 100")
    print(f"  Démarrage : {resultat['scores']['demarrage']} / {config.POINTS_DEMARRAGE}")
    print(f"  Disque    : {resultat['scores']['disque']} / {config.POINTS_DISQUE}")
    if not resultat["conseils"]:
        print("\nRien à signaler : votre PC est en bonne forme.")
    for numero, conseil in enumerate(resultat["conseils"], start=1):
        print(f"\n{numero}. {conseil}")


def main() -> None:
    print("=== Démarrage ===")
    resultats_demarrage = demarrage.scan()
    afficher_demarrage(resultats_demarrage)

    print("\n=== Disque ===")
    print("Analyse des dossiers en cours, cela peut prendre une minute...")
    resultats_disque = disque.scan()
    afficher_disque(resultats_disque)

    print("\n=== Bilan ===")
    afficher_score(score.calculer(resultats_demarrage, resultats_disque))


if __name__ == "__main__":
    main()
