"""Tests du module connexion, sans réseau : les mesures sont remplacées. Lancer avec : python -m pytest"""

import socket
import threading
import time

import pytest

from modules import connexion

WIFI = {"type": "wifi", "nom": "Wi-Fi", "vitesse": 1201, "wifi": {"signal": 78, "bande": "5 GHz", "norme": "Wi-Fi 6"}}


@pytest.fixture(autouse=True)
def reseau_interdit(monkeypatch):
    """Aucun test n'utilise le réseau : remplacer les mesures explicitement."""
    def interdit(*_):
        raise AssertionError("un test a tenté d'utiliser le réseau")
    for fonction in ("adresse_serveur", "telecharger", "envoyer"):
        monkeypatch.setattr(connexion, fonction, interdit)


def liaison(type_: str | None = "wifi", vitesse: int | None = 1201, signal: int = 78, bande: str | None = "5 GHz",
            norme: str | None = "Wi-Fi 6") -> dict:
    wifi = {"signal": signal, "bande": bande, "norme": norme} if type_ == "wifi" else None
    return {"type": type_, "nom": "Wi-Fi" if type_ else None, "vitesse": vitesse, "wifi": wifi}


def mesures(descendant: float = 500, montant: float = 250, ping: float = 20, gigue: float = 3, trafic: float = 0,
            lien: dict | None = None) -> dict:
    return {"liaison": lien or liaison(), "descendant": descendant, "montant": montant, "ping": ping, "gigue": gigue,
            "trafic": trafic}


def test_bande_d_apres_le_canal():
    assert connexion.bande(100, 10, 1201) == "5 GHz"  # le PC de l'utilisateur
    assert connexion.bande(6, 7, 144) == "2,4 GHz"
    assert connexion.bande(1, 10, 287) == "2,4 GHz"  # canal 1 en Wi-Fi 6 : 2,4 GHz à ce débit
    assert connexion.bande(1, 10, 1201) is None  # ou 6 GHz : on ne tranche pas
    assert connexion.bande(37, 10, 2402) == "6 GHz"  # pas de canal 37 en 5 GHz
    assert connexion.bande(149, 10, 1201) is None  # 5 ou 6 GHz
    assert connexion.bande(149, 8, 866) == "5 GHz"  # le Wi-Fi 5 n'a pas de 6 GHz
    assert connexion.bande(0, 7, 0) is None


def test_norme():
    assert connexion.norme(10, "6 GHz") == "Wi-Fi 6E"
    assert connexion.norme(10, "5 GHz") == connexion.norme(10, None) == "Wi-Fi 6"
    assert connexion.norme(8, None) == "Wi-Fi 5" and connexion.norme(11, None) == "Wi-Fi 7"
    assert connexion.norme(6, "2,4 GHz") == "ancien Wi-Fi (802.11g)"
    assert connexion.norme(99, None) is None


def test_liaison_reelle():
    """Lue auprès de Windows, sans rien envoyer : elle marche sur tout PC, relié à un réseau ou non."""
    lien = connexion.liaison()
    assert lien["type"] in (None, "wifi", "cable", "mobile", "autre")
    assert lien["wifi"] is None or 0 <= lien["wifi"]["signal"] <= 100


def test_gigue():
    assert connexion.gigue([20, 22, 21, 25]) == pytest.approx(7 / 3)
    assert connexion.gigue([20]) == 0


def test_debit_sans_la_montee_en_puissance():
    # 1 Mo la première seconde, puis 10 Mo par seconde : les 30 premiers % des données ne comptent pas.
    releves = [(0.0, 0), (1.0, 10**6), (2.0, 11 * 10**6), (3.0, 21 * 10**6), (4.0, 31 * 10**6)]
    assert connexion.debit_stable(releves) == pytest.approx(80)  # 20 Mo en 2 s
    # Mesure trop courte pour écarter le début : tout compte.
    assert connexion.debit_stable([(0.0, 0), (0.2, 10**6), (0.4, 3 * 10**6)]) == pytest.approx(60)
    assert connexion.debit_stable([(0.0, 0), (1.0, 0)]) is None


def flux_rapide(octets, numero, fini):
    """Faux flux : 64 Kio par milliseconde, jusqu'à la fin de la mesure."""
    while not fini():
        octets[numero] += connexion.BLOC
        time.sleep(0.001)


def test_mesure_du_debit(monkeypatch):
    monkeypatch.setattr(connexion, "DUREE_MESURE", 0.6)
    avances = []
    debit = connexion.mesurer_debit(flux_rapide, 10**12, lambda avance, _debit: avances.append(avance),
                                    lambda: False)
    assert debit > 0 and avances[-1] == pytest.approx(1, abs=0.2)
    time.sleep(0.05)
    assert not [fil for fil in threading.enumerate() if fil.name.startswith("debit-")]  # les flux se sont arrêtés


def test_mesure_arretee_a_la_limite_de_donnees(monkeypatch):
    monkeypatch.setattr(connexion, "DUREE_MESURE", 30)
    debut = time.perf_counter()
    assert connexion.mesurer_debit(flux_rapide, 2 * 10**6, lambda *_: None, lambda: False) > 0
    assert time.perf_counter() - debut < 5


def test_mesure_arretee_par_l_utilisateur():
    arret = threading.Event()
    threading.Timer(0.3, arret.set).start()
    assert connexion.mesurer_debit(flux_rapide, 10**12, lambda *_: None, arret.is_set) is None


def test_un_flux_qui_echoue_fait_echouer_la_mesure(monkeypatch):
    def flux_casse(octets, numero, fini):
        if numero == 2:
            raise connexion.Refus(429, "60")
        flux_rapide(octets, numero, fini)
    with pytest.raises(connexion.Refus):
        connexion.mesurer_debit(flux_casse, 10**12, lambda *_: None, lambda: False)


def test_refus_du_serveur():
    assert connexion.Refus(429, "3566").attente == 3566
    assert connexion.Refus(403, None).attente is None
    assert connexion.Refus(429, "Wed, 21 Oct 2026 07:28:00 GMT").attente is None

    class Reponse:
        status, reason = 429, "Too Many Requests"

        @staticmethod
        def getheader(nom):
            return {"Retry-After": "120"}.get(nom)
    with pytest.raises(connexion.Refus) as refus:
        connexion._verifier(Reponse())
    assert refus.value.attente == 120


def test_delai_lisible():
    assert connexion.delai_lisible(None) == "dans un moment"
    assert connexion.delai_lisible(20) == connexion.delai_lisible(60) == "dans une minute"
    assert connexion.delai_lisible(600) == "dans 10 minutes"
    assert connexion.delai_lisible(3566) == "dans une heure environ"
    assert connexion.delai_lisible(3 * 3600) == "dans 3 heures environ"


def faux_test(monkeypatch, ping=None, debits=(512.0, 255.0), lien=None):
    """Remplace les mesures du réseau ; renvoie les étapes annoncées par la progression."""
    monkeypatch.setattr(connexion, "liaison", lambda: lien or liaison())
    monkeypatch.setattr(connexion, "trafic", lambda _nom: None)

    def pings(progression, arret):
        progression(1.0, 20.0)
        return [20.0, 22.0, 19.0] if ping is None else ping()
    monkeypatch.setattr(connexion, "mesurer_ping", pings)
    restants = list(debits)

    def debit(_flux, _limite, progression, _arret):
        progression(1.0, restants[0])
        valeur = restants.pop(0)
        if isinstance(valeur, Exception):
            raise valeur
        return valeur
    monkeypatch.setattr(connexion, "mesurer_debit", debit)
    etapes = []
    return etapes, lambda etape, avance, valeur: etapes.append(etape)


def test_test_complet(monkeypatch):
    etapes, progression = faux_test(monkeypatch)
    resultat = connexion.scan(progression)
    assert etapes == ["ping", "descendant", "montant"]
    assert (resultat["ping"], resultat["descendant"], resultat["montant"]) == (20.0, 512.0, 255.0)
    assert resultat["gigue"] == pytest.approx(2.5) and resultat["trafic"] == 0
    assert all(possible for _usage, possible in resultat["usages"]) and resultat["conseils"] == []
    assert resultat["liaison"] == liaison()


def test_sans_reseau(monkeypatch):
    faux_test(monkeypatch, lien=liaison(None, None))
    resultat = connexion.scan()
    assert resultat["erreur"].startswith("Ton PC n'est relié à aucun réseau")


def test_serveur_injoignable(monkeypatch):
    def plante():
        raise socket.gaierror("nom inconnu")
    faux_test(monkeypatch, ping=plante)
    assert connexion.scan()["erreur"].startswith("Le serveur de test n'a pas répondu")


def test_trop_de_tests(monkeypatch):
    faux_test(monkeypatch, debits=(connexion.Refus(429, "3566"), 0))
    assert connexion.scan()["erreur"] == ("Le serveur de test de Cloudflare refuse les tests trop rapprochés depuis "
                                          "une même connexion : réessaie dans une heure environ.")


def test_test_arrete(monkeypatch):
    faux_test(monkeypatch, ping=lambda: None)
    assert connexion.scan() is None


def test_textes():
    assert connexion.nombre_debit(4.56) == "4,6" and connexion.nombre_debit(212.4) == "212"
    assert connexion.nombre_debit(1201) == "1\u202f201"
    assert [connexion.mot_signal(s) for s in (90, 70, 45, 20)] == ["excellent", "bon", "moyen", "faible"]
    assert [connexion.niveau(mesures(d))[:2] for d in (3, 20, 60, 500)] == [
        ("rouge", "Lente"), ("orange", "Correcte"), ("vert", "Rapide"), ("vert", "Très rapide")]


def test_usages():
    usages = dict((usage, condition(mesures(descendant=15, montant=2, ping=80)))
                  for usage, condition in connexion.USAGES)
    assert usages == {"Navigation web et e-mails": True, "Vidéo en HD (YouTube, Netflix…)": True,
                      "Vidéo en 4K": False, "Appels vidéo (Teams, Zoom, Discord…)": False, "Jeux en ligne": False,
                      "Envoi de gros fichiers (sauvegarde en ligne, vidéos)": False}


def test_conseils():
    assert connexion.conseils(mesures()) == []
    faible = connexion.conseils(mesures(descendant=6, lien=liaison(signal=32, bande="2,4 GHz", vitesse=72)))
    assert [texte[:27] for texte, _lien in faible] == ["Le signal Wi-Fi est faible ", "Ton PC est connecté au Wi-F"]
    assert faible[1][1] == connexion.LIEN_WIFI  # où choisir le réseau 5 GHz
    # Bon signal, mais une liaison qui plafonne : c'est elle qui limite.
    (plafond, _lien), = connexion.conseils(mesures(descendant=80, lien=liaison(vitesse=144)))
    assert plafond.startswith("La liaison Wi-Fi entre le PC et la box plafonne à 144 Mbit/s")
    (lent, _lien), = connexion.conseils(mesures(ping=120, gigue=8))
    assert lent.startswith("La connexion met du temps à réagir (ping de 120 ms")
    (fournisseur, _lien), = connexion.conseils(mesures(descendant=4, lien=liaison("cable", 1000)))
    assert fournisseur.startswith("Le débit est faible alors que la liaison avec la box est bonne")
    # Débit faible, mais c'est la liaison Wi-Fi qui limite : pas la faute du fournisseur.
    (sature, _lien), = connexion.conseils(mesures(descendant=8, lien=liaison(vitesse=12)))
    assert sature.startswith("La liaison Wi-Fi entre le PC et la box plafonne à 12 Mbit/s")
    tout = connexion.conseils(mesures(descendant=4, ping=150, lien=liaison(signal=30, bande="2,4 GHz")))
    assert len(tout) == 3  # trois au plus


def test_remarque_sur_le_trafic_deja_la():
    assert connexion.remarque(mesures(trafic=0.5)) is None
    assert connexion.remarque(mesures(trafic=4.2)).startswith("D'autres programmes utilisaient déjà la connexion "
                                                             "au début du test (environ 4,2 Mbit/s")


def test_description_de_la_liaison():
    assert connexion.description(liaison(None, None)) == [
        ("Connexion", "Aucune", "Le PC n'est relié à aucun réseau : active le Wi-Fi ou branche un câble.")]
    assert [nom for nom, _valeur, _detail in connexion.description(liaison())] == [
        "Connexion", "Signal Wi-Fi", "Type de Wi-Fi", "Vitesse de la liaison"]
    assert connexion.description(liaison())[1:3] == [("Signal Wi-Fi", "78 % (bon)", ""),
                                                    ("Type de Wi-Fi", "5 GHz · Wi-Fi 6", "")]
    cable = connexion.description(liaison("cable", 1000))
    assert cable[0][1] == "Câble réseau (Ethernet)" and cable[1][1] == "1\u202f000 Mbit/s"
    assert connexion.description(liaison(bande=None, norme=None, vitesse=None))[1:] == [
        ("Signal Wi-Fi", "78 % (bon)", "")]
