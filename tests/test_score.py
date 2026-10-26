"""Tests du calcul du score (v4). Lancer avec : python -m pytest"""

import os
import unittest
from datetime import date, timedelta

import config
from modules import score

GO = 1024**3


def demarrage(nb: int) -> dict:
    return {"programmes": [{"nom": f"p{i}", "editeur": None, "chemin": rf"C:\p{i}.exe", "source": "Registre"}
                           for i in range(nb)]}


def disque(pourcentage: float, gros_dossiers: list[dict] | None = None) -> dict:
    lecteur = os.environ.get("SystemDrive", "C:") + "\\"
    return {"disques": [{"disque": lecteur, "total": 100 * GO, "utilise": pourcentage * GO,
                         "libre": (100 - pourcentage) * GO, "pourcentage": pourcentage}],
            "gros_dossiers": gros_dossiers or []}


def ressources(ram: float = 40, cpu: float = 10, processus: list[dict] | None = None) -> dict:
    if processus is None:
        processus = [{"nom": "chrome.exe", "octets": 3 * GO}, {"nom": "Code.exe", "octets": 2 * GO}]
    return {"ram": {"total": 16 * GO, "utilise": 16 * GO * ram / 100, "pourcentage": ram}, "cpu": cpu,
            "processus": processus}


def fichiers(corbeille: float = 0, temporaires: float = 0, caches: float = 0, ancien_windows: float = 0) -> dict:
    """Tailles en Go, toutes sur le disque de Windows."""
    return {"corbeille": corbeille * GO, "temporaires": temporaires * GO,
            "navigateurs": {"Chrome": caches * GO} if caches else {}, "ancien_windows": ancien_windows * GO,
            "recuperable_systeme": (corbeille + temporaires + caches + ancien_windows) * GO}


def redemarrage(jours: float = 1, en_attente: bool = False) -> dict:
    return {"jours": jours, "en_attente": en_attente}


def alimentation(mode: int | None = 2, plan_economies: bool = False) -> dict:
    """Mode 2 : équilibré."""
    return {"mode": mode, "plan_economies": plan_economies}


def batterie(sante: float | None = 0.9) -> dict:
    return {"applicable": True, "niveau": 80, "branche": True, "sante": sante}


def jeux(frequence: int = 144, maximum: int = 144, age: int | None = 30, mode_jeu: bool = True,
         sur_batterie: bool = False, ecrans: list[dict] | None = None) -> dict:
    """Par défaut : écran à sa fréquence maximale, pilote d'un mois, Mode jeu activé."""
    carte = {"nom": "NVIDIA GeForce RTX 3060", "fabricant": "NVIDIA", "age": age, "memoire": 6 * GO,
             "date": date(2026, 10, 25) - timedelta(days=age or 0) if age is not None else None}
    if ecrans is None:
        ecrans = [{"principal": True, "largeur": 1920, "hauteur": 1080, "frequence": frequence, "maximum": maximum}]
    return {"ecrans": ecrans, "cartes": [carte], "carte_jeux": carte, "mode_jeu": mode_jeu,
            "sur_batterie": sur_batterie}


def pilotes(nvidia: dict | None = None, mises_a_jour: list[dict] | None = None, anciens: int = 0,
            outil: dict | None = None) -> dict:
    """Par défaut : rien à mettre à jour, rien de vieux. `nvidia` : voir modules/pilotes.verifier_nvidia."""
    vieux = [{"nom": f"Pilote {i}", "categorie": categorie, "fournisseur": "Realtek", "version": "1.0",
              "date": date(2022, 5, 16), "age": 1624}
             for i, categorie in enumerate(["Réseau", "Son", "Carte mère et processeur", "Bluetooth"][:anciens])]
    mises_a_jour = mises_a_jour or []
    a_jour = nvidia is None or not nvidia["derniere"] or nvidia["derniere"]["version"] == nvidia["installee"]
    return {"nvidia": nvidia, "mises_a_jour": mises_a_jour, "anciens": vieux, "pilotes": vieux, "outil": outil,
            "fabricant": "ASUSTeK COMPUTER INC.", "bloques": False, "a_installer": len(mises_a_jour) + (not a_jour)}


def pc(**modules) -> dict:
    """Résultats d'un PC en forme, sans batterie, où l'on remplace certains modules."""
    return {"demarrage": demarrage(5), "disque": disque(40), "ressources": ressources(),
            "redemarrage": redemarrage()} | modules


class TestBareme(unittest.TestCase):
    def test_lineaire(self):
        self.assertEqual(score.lineaire(50, 70, 95), 1)
        self.assertEqual(score.lineaire(70, 70, 95), 1)
        self.assertEqual(score.lineaire(82.5, 70, 95), 0.5)
        self.assertEqual(score.lineaire(95, 70, 95), 0)
        self.assertEqual(score.lineaire(100, 70, 95), 0)

    def test_total_100(self):
        self.assertEqual(sum(config.POINTS_AVEC_BATTERIE.values()), 100)
        self.assertEqual(sum(config.POINTS_SANS_BATTERIE.values()), 100)

    def test_version(self):
        self.assertEqual(score.calculer(pc())["version"], config.SCORE_VERSION)


class TestBatterie(unittest.TestCase):
    def test_pas_de_batterie(self):
        resultat = score.calculer(pc())
        self.assertEqual(resultat["bareme"], config.POINTS_SANS_BATTERIE)
        self.assertEqual(resultat["score"], 100)
        self.assertNotIn("batterie", resultat["scores"])

    def test_batterie_non_applicable(self):
        resultat = score.calculer(pc(batterie={"applicable": False}))
        self.assertEqual(resultat["bareme"], config.POINTS_SANS_BATTERIE)
        self.assertEqual(resultat["score"], 100)

    def test_batterie_saine(self):
        resultat = score.calculer(pc(batterie=batterie(0.9)))
        self.assertEqual(resultat["bareme"], config.POINTS_AVEC_BATTERIE)
        self.assertEqual(resultat["score"], 100)

    def test_usure_non_mesurable_hors_score(self):
        resultat = score.calculer(pc(batterie=batterie(None)))
        self.assertEqual(resultat["bareme"], config.POINTS_SANS_BATTERIE)
        self.assertEqual(resultat["score"], 100)

    def test_batterie_usee(self):
        # Usure 50 % : entre 20 et 60 % -> 1/4 des 15 points (3,75 arrondi à 4).
        resultat = score.calculer(pc(batterie=batterie(0.5)))
        self.assertEqual(resultat["scores"]["batterie"], 4)
        self.assertEqual(resultat["score"], 25 + 25 + 20 + 15 + 4)
        self.assertIn("50 % de sa capacité", resultat["conseils"][0])


class TestRedemarrage(unittest.TestCase):
    def test_seuils(self):
        points = lambda jours: score.calculer(pc(redemarrage=redemarrage(jours)))["scores"]["redemarrage"]
        self.assertEqual(points(7), 15)
        self.assertEqual(points(18.5), 8)  # à mi-chemin entre 7 et 30 jours : 7,5 arrondi
        self.assertEqual(points(30), 0)

    def test_mise_a_jour_en_attente(self):
        resultat = score.calculer(pc(redemarrage=redemarrage(1, en_attente=True)))
        self.assertEqual(resultat["scores"]["redemarrage"], 8)  # plafonné à la moitié des 15 points
        conseil = resultat["conseils"][0]
        self.assertIn("mise à jour", conseil)
        self.assertIn("Redémarrer", conseil)
        self.assertNotIn("n'a pas redémarré depuis", conseil)  # redémarré hier : on n'en parle pas

    def test_longtemps_sans_redemarrer(self):
        conseil = score.calculer(pc(redemarrage=redemarrage(20)))["conseils"][0]
        self.assertIn("depuis 20 jours", conseil)
        self.assertIn("« Arrêter » ne suffit pas", conseil)
        self.assertNotIn("mise à jour", conseil)


class TestFichiers(unittest.TestCase):
    def test_hors_score(self):
        resultat = score.calculer(pc(fichiers=fichiers(50, 5)))
        self.assertEqual(resultat["score"], 100)
        self.assertNotIn("fichiers", resultat["scores"])
        self.assertEqual(resultat["conseils"], [])  # disque à 40 % : rien à gagner, pas de conseil

    def test_conseil_quand_le_disque_est_plein(self):
        # Disque à 90 % de 100 Go : libérer 10 Go le ramène à 80 % -> 30 x (0,6 - 0,2) = 12 points regagnés.
        resultat = score.calculer(pc(disque=disque(90), fichiers=fichiers(8, 2)))
        conseil = resultat["conseils"][1]  # après le conseil disque (24 points)
        self.assertTrue(conseil.startswith("La Corbeille contient 8,0 Go et les fichiers temporaires occupent 2,0 Go"))
        self.assertIn("rien d'important", conseil)  # prudence : vider la Corbeille est définitif

    def test_cache_des_navigateurs(self):
        conseil = score.calculer(pc(disque=disque(90), fichiers=fichiers(8, 2, caches=1)))["conseils"][1]
        self.assertTrue(conseil.startswith("La Corbeille contient 8,0 Go, les fichiers temporaires occupent 2,0 Go "
                                           "et le cache des navigateurs 1,0 Go"))
        self.assertIn("« Images et fichiers en cache »", conseil)  # pas les mots de passe ni l'historique
        self.assertNotIn("ancienne version de Windows", conseil)

    def test_ancienne_version_de_windows(self):
        conseil = score.calculer(pc(disque=disque(90), fichiers=fichiers(0, 2, ancien_windows=20)))["conseils"][1]
        self.assertTrue(conseil.startswith("Les fichiers temporaires occupent 2,0 Go et l'ancienne version de "
                                           "Windows environ 20,0 Go"))
        self.assertIn("tu ne pourras plus revenir en arrière", conseil)  # prudence : c'est définitif

    def test_corbeille_vide(self):
        conseil = score.calculer(pc(disque=disque(90), fichiers=fichiers(0, 10)))["conseils"][1]
        self.assertTrue(conseil.startswith("Les fichiers temporaires occupent 10,0 Go"))

    def test_trop_peu_pour_un_conseil(self):
        # 100 Mo sur 100 Go : moins d'un point à regagner.
        resultat = score.calculer(pc(disque=disque(90), fichiers=fichiers(0, 0.1)))
        self.assertEqual(len(resultat["conseils"]), 1)


class TestAlimentation(unittest.TestCase):
    def test_hors_score_et_sans_conseil_si_equilibre(self):
        resultat = score.calculer(pc(alimentation=alimentation(2)))
        self.assertEqual(resultat["score"], 100)
        self.assertNotIn("alimentation", resultat["scores"])
        self.assertEqual(resultat["conseils"], [])

    def test_mode_illisible(self):
        self.assertEqual(score.calculer(pc(alimentation=alimentation(None)))["conseils"], [])

    def test_economiseur(self):
        resultat = score.calculer(pc(alimentation=alimentation(0)))
        self.assertEqual(resultat["score"], 100)  # hors score : le conseil n'enlève aucun point
        self.assertIn("L'économiseur d'énergie est activé", resultat["conseils"][0])
        self.assertIn("utile sur batterie", resultat["conseils"][0])  # pas un réglage à couper à tout prix

    def test_plan_economies(self):
        conseil = score.calculer(pc(alimentation=alimentation(2, plan_economies=True)))["conseils"][0]
        self.assertIn("« Utilisation normale »", conseil)

    def test_efficacite(self):
        conseil = score.calculer(pc(alimentation=alimentation(1)))["conseils"][0]
        self.assertIn("choisis « Équilibré »", conseil)

    def test_economiseur_avant_le_plan(self):
        conseils = score.calculer(pc(alimentation=alimentation(0, plan_economies=True)))["conseils"]
        self.assertEqual(len(conseils), 1)
        self.assertIn("économiseur", conseils[0])

    def test_place_parmi_les_conseils(self):
        # Disque à 90 % : 24 points à regagner, avant l'alimentation (10).
        conseils = score.calculer(pc(disque=disque(90), alimentation=alimentation(1)))["conseils"]
        self.assertIn("Ton disque", conseils[0])
        self.assertIn("efficacité énergétique", conseils[1])


class TestDisqueDur(unittest.TestCase):
    def test_hdd(self):
        resultat = score.calculer(pc(disque={**disque(40), "systeme_hdd": True},
                                     alimentation=alimentation(1)))
        self.assertEqual(resultat["score"], 100)  # hors score
        self.assertIn("disque dur classique (HDD)", resultat["conseils"][0])  # avant l'alimentation (10)
        self.assertIn("efficacité énergétique", resultat["conseils"][1])

    def test_ssd_ou_inconnu(self):
        for valeur in (False, None):
            self.assertEqual(score.calculer(pc(disque={**disque(40), "systeme_hdd": valeur}))["conseils"], [])


class TestMemoireInstallee(unittest.TestCase):
    def test_peu_de_memoire(self):
        resultat = score.calculer(pc(ressources={**ressources(), "installee": 4 * GO}))
        self.assertEqual(resultat["score"], 100)  # hors score
        self.assertIn("n'a que 4 Go de mémoire vive", resultat["conseils"][0])

    def test_8_go_suffisent(self):
        self.assertEqual(score.calculer(pc(ressources={**ressources(), "installee": 8 * GO}))["conseils"], [])

    def test_inconnue(self):
        self.assertEqual(score.calculer(pc(ressources={**ressources(), "installee": None}))["conseils"], [])


class TestCasExtremes(unittest.TestCase):
    def test_ram_a_95(self):
        resultat = score.calculer(pc(ressources=ressources(ram=95)))
        self.assertEqual(resultat["scores"]["ressources"], 12)  # RAM à 0, processeur au maximum : 12,5 arrondi
        self.assertEqual(resultat["score"], 30 + 30 + 12 + 15)
        conseil = resultat["conseils"][0]
        self.assertIn("95 %", conseil)
        self.assertIn("chrome (3,0 Go)", conseil)
        self.assertIn("antivirus", conseil)  # prudence : certains programmes doivent rester ouverts

    def test_ram_pleine_sans_processus_lisible(self):
        conseil = score.calculer(pc(ressources=ressources(ram=95, processus=[])))["conseils"][0]
        self.assertNotIn("Ceux qui en prennent le plus", conseil)

    def test_processeur_occupe(self):
        resultat = score.calculer(pc(ressources=ressources(cpu=100)))
        self.assertEqual(resultat["scores"]["ressources"], 12)
        self.assertIn("Gestionnaire des tâches", resultat["conseils"][0])

    def test_disque_plein_a_99(self):
        resultat = score.calculer(pc(disque=disque(99)))
        self.assertEqual(resultat["scores"]["disque"], 0)
        self.assertEqual(resultat["score"], 70)
        self.assertIn("plein à 99 %", resultat["conseils"][0])
        self.assertIn("Un disque presque plein ralentit Windows.", resultat["conseils"][0])

    def test_disque_bien_rempli_mais_pas_presque_plein(self):
        conseil = score.calculer(pc(disque=disque(80)))["conseils"][0]
        self.assertIn("plein à 80 %", conseil)
        self.assertNotIn("presque plein", conseil)  # à 80 %, il reste de la marge : pas d'alarme
        self.assertIn("mieux vaut garder de la marge", conseil)
        self.assertIn("L'onglet Stockage", conseil)

    def test_40_programmes(self):
        resultat = score.calculer(pc(demarrage=demarrage(40)))
        self.assertEqual(resultat["scores"]["demarrage"], 0)  # plancher : jamais négatif
        self.assertIn("40 programmes", resultat["conseils"][0])

    def test_tout_au_pire(self):
        gros = [{"chemin": r"C:\Users\moi\Videos", "taille": 200 * GO}]
        resultat = score.calculer({"demarrage": demarrage(40), "disque": disque(99, gros),
                                   "ressources": ressources(ram=99, cpu=100), "redemarrage": redemarrage(40, True),
                                   "batterie": batterie(0.3)})
        self.assertEqual(resultat["score"], 0)
        self.assertEqual(len(resultat["conseils"]), config.NB_CONSEILS_MAX)

    def test_aucune_donnee(self):
        resultat = score.calculer({"demarrage": {"programmes": []}, "disque": {"disques": [], "gros_dossiers": []},
                                   "ressources": ressources(ram=0, cpu=0, processus=[]),
                                   "redemarrage": redemarrage(0)})
        self.assertEqual(resultat["score"], 100)
        self.assertEqual(resultat["conseils"], [])

    def test_tous_modules_en_erreur(self):
        resultat = score.calculer({"demarrage": None, "disque": None, "ressources": None, "batterie": None})
        self.assertIsNone(resultat["score"])
        self.assertEqual(resultat["scores"], {})
        self.assertEqual(resultat["conseils"], [])

    def test_un_module_en_erreur(self):
        resultat = score.calculer(pc(disque=None, demarrage=demarrage(40)))
        self.assertIsNone(resultat["score"])  # score global trompeur sans le disque
        self.assertEqual(resultat["scores"], {"demarrage": 0, "ressources": 25, "redemarrage": 15})
        self.assertIn("40 programmes", resultat["conseils"][0])

    def test_module_manquant(self):
        self.assertIsNone(score.calculer({})["score"])


class TestConseils(unittest.TestCase):
    def test_tries_par_impact(self):
        # Démarrage : -3,5 points ; disque à 90 % : -24 points -> le disque passe en premier.
        gros = [{"chemin": r"C:\Users\moi\AppData", "taille": 80 * GO},
                {"chemin": r"C:\Users\moi\Downloads", "taille": 30 * GO}]
        resultat = score.calculer(pc(demarrage=demarrage(12), disque=disque(90, gros)))
        self.assertEqual(resultat["score"], 26 + 6 + 25 + 15)
        conseils = resultat["conseils"]
        self.assertEqual(len(conseils), 3)
        self.assertIn("plein à 90 %", conseils[0])
        self.assertIn("Téléchargements", conseils[1])  # AppData n'est jamais proposé
        self.assertIn("12 programmes", conseils[2])
        # Un bouton « Ouvrir » par conseil, dans le même ordre.
        self.assertEqual(resultat["liens"], [score.LIEN_STOCKAGE, ("Ouvrir le dossier", r"C:\Users\moi\Downloads"),
                                             score.LIEN_DEMARRAGE])

    def test_liens_selon_le_cas(self):
        def lien(**modules):
            return score.calculer(pc(**modules))["liens"][0]
        self.assertEqual(lien(redemarrage=redemarrage(20)), None)  # redémarrer : depuis le menu Démarrer
        self.assertEqual(lien(redemarrage=redemarrage(1, en_attente=True)), score.LIEN_MISES_A_JOUR)
        self.assertEqual(lien(ressources=ressources(ram=95)), score.LIEN_GESTIONNAIRE)
        self.assertEqual(lien(alimentation=alimentation(2, plan_economies=True)), score.LIEN_OPTIONS_ALIMENTATION)
        self.assertEqual(lien(alimentation=alimentation(0)), score.LIEN_ALIMENTATION)
        self.assertEqual(lien(batterie=batterie(0.3)), None)

    def test_demarrage_prudent(self):
        conseil = score.calculer(pc(demarrage=demarrage(20)))["conseils"][0]
        self.assertIn("antivirus", conseil)
        self.assertIn("pilotes", conseil)

    def test_gros_dossier_sous_le_seuil(self):
        petit = [{"chemin": r"C:\Users\moi\Downloads", "taille": 4 * GO}]
        conseils = score.calculer(pc(disque=disque(90, petit)))["conseils"]
        self.assertEqual(len(conseils), 1)  # seul le conseil disque, pas celui du dossier

    def test_petite_perte_sans_conseil(self):
        # RAM à 71 % : moins d'un point perdu, pas de quoi déranger avec un conseil.
        resultat = score.calculer(pc(ressources=ressources(ram=71)))
        self.assertEqual(resultat["conseils"], [])

    def test_disque_systeme_absent(self):
        resultat = score.calculer(pc(disque={"disques": [], "gros_dossiers": []}))
        self.assertEqual(resultat["scores"]["disque"], 30)


class TestJeux(unittest.TestCase):
    """Jeux et affichage : hors score, des conseils à poids fixe."""

    def test_rien_a_regler(self):
        resultat = score.calculer(pc(jeux=jeux()))
        self.assertEqual((resultat["score"], resultat["conseils"]), (100, []))
        self.assertNotIn("jeux", resultat["scores"])  # hors score

    def test_ecran_sous_sa_frequence(self):
        resultat = score.calculer(pc(jeux=jeux(frequence=60, maximum=144)))
        self.assertEqual(resultat["score"], 100)  # le score ne bouge pas
        self.assertIn("Ton écran affiche 60 images par seconde (Hz), alors qu'il peut aller jusqu'à 144 Hz",
                      resultat["conseils"][0])
        self.assertEqual(resultat["liens"], [score.LIEN_ECRAN])
        self.assertNotIn("batterie", resultat["conseils"][0])

    def test_ecran_presque_a_son_maximum(self):
        for frequence, maximum in ((59, 60), (144, 165)):  # arrondi de 59,94 Hz ; écart trop faible
            self.assertEqual(score.conseils_jeux(jeux(frequence=frequence, maximum=maximum)), [])

    def test_ecran_sur_batterie(self):
        conseil = score.conseils_jeux(jeux(frequence=60, maximum=165, sur_batterie=True))[0][1]
        self.assertIn("Sur batterie, une fréquence plus basse économise de l'énergie", conseil)

    def test_deuxieme_ecran(self):
        ecrans = [{"principal": True, "largeur": 2560, "hauteur": 1440, "frequence": 165, "maximum": 165},
                  {"principal": False, "largeur": 1920, "hauteur": 1080, "frequence": 60, "maximum": 144},
                  {"principal": False, "largeur": 1920, "hauteur": 1080, "frequence": 60, "maximum": 75}]
        conseils = score.conseils_jeux(jeux(ecrans=ecrans))
        self.assertEqual(len(conseils), 1)  # un seul conseil d'écran
        self.assertTrue(conseils[0][1].startswith("Ton écran 2 affiche 60"))

    def test_vieux_pilote(self):
        self.assertEqual(score.conseils_jeux(jeux(age=config.PILOTE_GRAPHIQUE_AGE_MAX)), [])
        conseil = score.conseils_jeux(jeux(age=400))[0]
        self.assertEqual(conseil[0], config.PILOTE_GRAPHIQUE_IMPACT)
        self.assertIn("il y a 13 mois", conseil[1])
        self.assertIn("NVIDIA App", conseil[1])
        self.assertIn("il y a plus de 4 ans", score.conseils_jeux(jeux(age=1488))[0][1])
        self.assertEqual(score.conseils_jeux(jeux(age=None)), [])  # date du pilote inconnue : rien à dire

    def test_mode_jeu_coupe(self):
        conseils = score.conseils_jeux(jeux(mode_jeu=False))
        self.assertEqual([(impact, lien) for impact, _, lien in conseils],
                         [(config.MODE_JEU_IMPACT, score.LIEN_MODE_JEU)])

    def test_ordre_parmi_les_autres_conseils(self):
        resultat = score.calculer(pc(jeux=jeux(frequence=60, maximum=144, age=400, mode_jeu=False),
                                     alimentation=alimentation(mode=1)))
        self.assertEqual(len(resultat["conseils"]), config.NB_CONSEILS_MAX)
        self.assertEqual(resultat["liens"], [score.LIEN_ALIMENTATION, score.LIEN_ECRAN, None])  # 10, 9, puis 5


def nvidia(installee: str = "617.14", derniere: str | None = "621.01") -> dict:
    """La carte de jeux() (NVIDIA GeForce RTX 3060), vérifiée auprès de NVIDIA (voir modules/pilotes)."""
    return {"carte": "NVIDIA GeForce RTX 3060", "installee": installee,
            "derniere": derniere and {"version": derniere, "date": date(2026, 10, 21), "url": "", "taille": 0}}


class TestPilotes(unittest.TestCase):
    """Pilotes : hors score, un conseil pour ce qui s'installe d'un clic, un autre pour ce qui est à vérifier."""

    def test_rien_a_faire(self):
        resultat = score.calculer(pc(pilotes=pilotes(nvidia=nvidia(derniere="617.14"))))
        self.assertEqual((resultat["score"], resultat["conseils"]), (100, []))
        self.assertNotIn("pilotes", resultat["scores"])  # hors score

    def test_nvidia_et_windows_update(self):
        garmin = [{"id": "x", "nom": "Garmin USB GPS"}]
        resultat = score.calculer(pc(pilotes=pilotes(nvidia=nvidia(), mises_a_jour=garmin)))
        self.assertEqual(resultat["score"], 100)
        self.assertEqual(resultat["liens"], [score.LIEN_PILOTES])
        self.assertEqual(resultat["conseils"][0],
                         "Une nouvelle version du pilote de ta carte graphique NVIDIA est sortie (621.01, tu as la "
                         "617.14) : les pilotes récents corrigent des bugs et rendent les jeux récents plus fluides. "
                         "Windows Update propose aussi 1 pilote (Garmin USB GPS). Le bouton installe tout d'un coup : "
                         "Windows te demandera l'autorisation et l'écran peut clignoter un instant.")

    def test_windows_update_seul_passe_apres_les_vrais_freins(self):
        garmin = [{"id": "x", "nom": "Garmin USB GPS"}]
        resultat = score.calculer(pc(pilotes=pilotes(mises_a_jour=garmin), ressources=ressources(ram=85)))
        self.assertEqual(resultat["liens"], [score.LIEN_GESTIONNAIRE, score.LIEN_PILOTES])  # la mémoire d'abord
        ((impact, _texte, lien),) = score.conseils_pilotes(pilotes(mises_a_jour=garmin))
        self.assertEqual((impact, lien), (config.PILOTES_WINDOWS_UPDATE_IMPACT, score.LIEN_PILOTES))
        ((impact, _texte, _lien),) = score.conseils_pilotes(pilotes(nvidia=nvidia(), mises_a_jour=garmin))
        self.assertEqual(impact, config.PILOTES_IMPACT)  # une nouvelle version NVIDIA reste prioritaire

    def test_un_seul_pilote(self):
        conseil = score.conseil_pilotes(pilotes(mises_a_jour=[{"id": "x", "nom": "Garmin USB GPS"}]))
        self.assertEqual(conseil, "Windows Update propose 1 pilote (Garmin USB GPS). Le bouton installe ce pilote : "
                                  "Windows te demandera l'autorisation.")

    def test_windows_update_seul(self):
        conseil = score.conseil_pilotes(pilotes(mises_a_jour=[{"id": "x", "nom": "A"}, {"id": "y", "nom": "B"}]))
        self.assertEqual(conseil, "Windows Update propose 2 pilotes (A, B). Le bouton installe tout d'un coup : "
                                  "Windows te demandera l'autorisation.")

    def test_vieux_pilotes(self):
        myasus = {"nom": "MyASUS", "cible": r"shell:AppsFolder\B9ECED6F.ASUSPCAssistant_qmba6cd70vzyy!App"}
        ((impact, texte, lien),) = score.conseils_pilotes(pilotes(anciens=4, outil=myasus))
        self.assertEqual((impact, lien), (config.PILOTES_ANCIENS_IMPACT, ("Ouvrir MyASUS", myasus["cible"])))
        self.assertTrue(texte.startswith("4 pilotes de ton PC (réseau, son, carte mère et processeur…) ont plus de "
                                         "2 ans. MyASUS, l'application du fabricant"))
        ((_, texte, lien),) = score.conseils_pilotes(pilotes(anciens=1))
        self.assertIsNone(lien)  # pas d'application du fabricant : son site
        self.assertTrue(texte.startswith("1 pilote de ton PC (réseau) a plus de 2 ans. Le site du fabricant de ton PC "
                                         "(ASUSTeK COMPUTER INC.), à la page d'assistance de ton modèle"))

    def test_l_age_du_pilote_ne_compte_plus_si_nvidia_a_repondu(self):
        vieux = jeux(age=400)
        self.assertEqual(len(score.conseils_jeux(vieux, pilotes(nvidia=nvidia()))), 0)
        self.assertEqual(len(score.conseils_jeux(vieux, pilotes(nvidia=nvidia(derniere=None)))), 1)  # hors ligne
        self.assertEqual(len(score.conseils_jeux(vieux, pilotes())), 1)  # pas une carte NVIDIA

    def test_ordre_parmi_les_autres_conseils(self):
        resultat = score.calculer(pc(pilotes=pilotes(nvidia=nvidia(), anciens=2), alimentation=alimentation(mode=1)))
        self.assertEqual([impact for impact in (config.ALIMENTATION_IMPACT, config.PILOTES_IMPACT,
                                                config.PILOTES_ANCIENS_IMPACT)], [10, 7, 4])
        self.assertEqual(resultat["liens"][:2], [score.LIEN_ALIMENTATION, score.LIEN_PILOTES])


if __name__ == "__main__":
    unittest.main()
