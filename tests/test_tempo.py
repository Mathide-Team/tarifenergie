"""Tempo (#340, #355) : historique réel des couleurs, règles, estimation des jours manquants, calcul."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from custom_components.tarifenergie.calcul import comparer, cout_option
from custom_components.tarifenergie.calendrier import (
    POSTES_TEMPO,
    CalendrierTempo,
    DonneesManquantes,
    PlagesHC,
    calendrier_pour,
)
from custom_components.tarifenergie.modele import Grille, Grilles, TarifIntrouvable
from custom_components.tarifenergie.tempo import (
    BLANC,
    BLEU,
    ROUGE,
    Climatologie,
    CouleurInconnue,
    CouleursInvalides,
    CouleursTempo,
    estimer,
    jour_tempo,
    jours_feries,
    jours_utiles,
    lire_couleurs,
    quotas,
    rouge_possible,
    saison,
    verifier_regles,
)

HISTORIQUE = lire_couleurs()
CLIMATOLOGIE = Climatologie.depuis(HISTORIQUE)
PLAGES = PlagesHC.lire("02:00-07:00")  # plages du compteur : ignorées par Tempo


def _jours(debut: date, fin: date) -> list[date]:
    return [debut + timedelta(days=i) for i in range((fin - debut).days + 1)]


# --- Règles et calendrier civil ---------------------------------------------------------


@pytest.mark.parametrize(
    ("annee", "lundi_paques"),
    [
        (2016, date(2016, 3, 28)),
        (2024, date(2024, 4, 1)),
        (2025, date(2025, 4, 21)),
        (2026, date(2026, 4, 6)),
    ],
)
def test_lundi_de_paques(annee, lundi_paques):
    assert lundi_paques in jours_feries(annee)


def test_jours_feries_2026():
    feries = jours_feries(2026)
    assert len(feries) == 11
    assert {date(2026, 5, 14), date(2026, 5, 25), date(2026, 11, 11), date(2026, 12, 25)} <= feries


def test_rouge_possible():
    assert rouge_possible(date(2025, 12, 1))  # lundi de décembre
    assert not rouge_possible(date(2025, 12, 6))  # samedi
    assert not rouge_possible(date(2025, 12, 7))  # dimanche
    assert not rouge_possible(date(2025, 12, 25))  # Noël
    assert not rouge_possible(date(2016, 3, 28))  # lundi de Pâques en mars
    assert not rouge_possible(date(2025, 10, 31))  # avant le 1er novembre
    assert not rouge_possible(date(2026, 4, 1))  # après le 31 mars


def test_saison():
    assert saison(date(2026, 8, 31)) == 2025
    assert saison(date(2026, 9, 1)) == 2026
    assert quotas(2025) == (22, 43)
    assert quotas(2019) == (18, 47)  # décision CRE (crise sanitaire)


def test_jour_tempo_de_6h_a_6h():
    assert jour_tempo(datetime(2026, 1, 10, 5)) == date(2026, 1, 9)
    assert jour_tempo(datetime(2026, 1, 10, 6)) == date(2026, 1, 10)
    assert jours_utiles([date(2026, 1, 10)]) == {date(2026, 1, 9), date(2026, 1, 10)}


# --- Historique réel livré (tarifs/tempo_couleurs.csv) ------------------------------------


def test_historique_complet_et_conforme():
    """Un jour par ligne depuis le 1er septembre 2014, sans trou, conforme aux règles."""
    jours = sorted(HISTORIQUE)
    assert jours[0] == date(2014, 9, 1)
    assert len(jours) == (jours[-1] - jours[0]).days + 1
    assert verifier_regles(HISTORIQUE) == []


@pytest.mark.parametrize("annee", range(2014, 2026))
def test_saisons_completes_aux_quotas(annee):
    couleurs = [c for j, c in HISTORIQUE.items() if saison(j) == annee]
    assert (couleurs.count(ROUGE), couleurs.count(BLANC)) == quotas(annee)


@pytest.mark.parametrize(
    ("jour", "couleur"),
    [
        # Jours publiés (RTE ; relevés de presse) : rouges de janvier 2020 et 2025, blanc d'un samedi.
        (date(2020, 1, 6), ROUGE),
        (date(2020, 3, 6), ROUGE),
        (date(2020, 3, 9), BLANC),
        (date(2025, 1, 17), ROUGE),
        (date(2025, 1, 18), BLANC),
        (date(2025, 1, 19), BLEU),
    ],
)
def test_jours_connus(jour, couleur):
    assert HISTORIQUE[jour] == couleur


@pytest.mark.parametrize(
    ("contenu", "message"),
    [
        ("date;couleur\n2026-13-01;bleu\n", "date illisible"),
        ("date;couleur\n2026-10-01;vert\n", "couleur inconnue"),
        ("date;couleur\n2026-10-01;bleu\n2026-10-01;bleu\n", "en double"),
    ],
)
def test_fichier_invalide(tmp_path, contenu, message):
    fichier = tmp_path / "c.csv"
    fichier.write_text(contenu, encoding="utf-8")
    with pytest.raises(CouleursInvalides, match=message):
        lire_couleurs(fichier)


def test_regles_enfreintes():
    erreurs = verifier_regles(
        {
            date(2025, 12, 6): ROUGE,  # samedi
            date(2025, 11, 11): ROUGE,  # férié
            date(2025, 10, 15): ROUGE,  # octobre
            date(2025, 12, 7): BLANC,  # dimanche
        }
    )
    assert any("2025-12-06 : rouge interdit" in e for e in erreurs)
    assert any("2025-11-11 : rouge interdit" in e for e in erreurs)
    assert any("2025-10-15 : rouge interdit" in e for e in erreurs)
    assert "2025-12-07 : blanc interdit le dimanche" in erreurs


def test_quotas_et_serie_depasses():
    # Six jours rouges d'affilée (le samedi est interdit en plus) puis 23 rouges dans la saison.
    serie = dict.fromkeys(_jours(date(2025, 12, 1), date(2025, 12, 6)), ROUGE)
    ouvres = [j for j in _jours(date(2026, 1, 5), date(2026, 3, 31)) if rouge_possible(j)][:17]
    blancs = dict.fromkeys(
        [j for j in _jours(date(2025, 9, 1), date(2026, 8, 31)) if j.weekday() < 5][-44:], BLANC
    )
    erreurs = verifier_regles({**serie, **dict.fromkeys(ouvres, ROUGE), **blancs})
    assert "2025-12-06 : plus de 5 rouges consécutifs" in erreurs
    assert "saison 2025-2026 : 23 rouges (quota 22)" in erreurs
    assert "saison 2025-2026 : 44 blancs (quota 43)" in erreurs


# --- Estimation des jours manquants -------------------------------------------------------


def test_aucun_manque_aucune_estimation():
    jours = _jours(date(2026, 1, 1), date(2026, 1, 31))
    couleurs = estimer(HISTORIQUE, jours, climatologie=CLIMATOLOGIE)
    assert couleurs.estimes == frozenset()
    assert couleurs.couleur(date(2026, 1, 5)) == ROUGE


def test_trou_en_janvier_estime_selon_les_regles():
    """Deux semaines de janvier 2026 retirées : couleurs estimées, règles et quota respectés."""
    trou = _jours(date(2026, 1, 5), date(2026, 1, 18))
    historique = {j: c for j, c in HISTORIQUE.items() if j not in trou}
    couleurs = estimer(historique, trou)  # climatologie recalculée depuis l'historique
    assert couleurs.estimes == frozenset(trou)
    estimees = {j: couleurs.couleur(j) for j in trou}
    rouges = [j for j, c in estimees.items() if c == ROUGE]
    assert rouges, "mi-janvier : la période la plus froide doit recevoir des rouges"
    assert all(rouge_possible(j) for j in rouges)
    assert all(j.weekday() != 6 for j, c in estimees.items() if c == BLANC)
    saison_complete = {**historique, **estimees}
    assert verifier_regles({j: c for j, c in saison_complete.items() if saison(j) == 2025}) == []


def test_quota_epuise_pas_de_rouge():
    """Saison 2024-2025 : 22 rouges déjà connus ; un trou en février ne reçoit aucun rouge."""
    trou = [j for j in _jours(date(2025, 2, 10), date(2025, 2, 14)) if HISTORIQUE[j] != ROUGE]
    historique = {j: c for j, c in HISTORIQUE.items() if j not in trou}
    rouges_connus = sum(1 for j, c in historique.items() if saison(j) == 2024 and c == ROUGE)
    assert rouges_connus == 22
    couleurs = estimer(historique, trou, climatologie=CLIMATOLOGIE)
    assert ROUGE not in {couleurs.couleur(j) for j in trou}


def test_ete_tout_bleu():
    trou = _jours(date(2025, 7, 1), date(2025, 7, 31))
    historique = {j: c for j, c in HISTORIQUE.items() if j not in trou}
    couleurs = estimer(historique, trou, climatologie=CLIMATOLOGIE)
    assert {couleurs.couleur(j) for j in trou} == {BLEU}


def test_saison_entiere_estimee():
    """Saison 2024-2025 entièrement retirée : environ 22 rouges et 43 blancs, aux bons endroits."""
    trou = _jours(date(2024, 9, 1), date(2025, 8, 31))
    historique = {j: c for j, c in HISTORIQUE.items() if j not in trou}
    couleurs = estimer(historique, trou)
    estimees = [couleurs.couleur(j) for j in trou]
    assert 20 <= estimees.count(ROUGE) <= 22
    assert 38 <= estimees.count(BLANC) <= 43
    assert verifier_regles(dict(zip(trou, estimees, strict=True))) == []


def test_jours_les_plus_froids_d_abord():
    """Avec une mesure de froid (rigueur), les rouges vont aux jours les plus froids."""
    semaine = _jours(date(2031, 1, 13), date(2031, 1, 17))  # du lundi au vendredi, hors historique
    rigueur = {j: float(i) for i, j in enumerate(semaine)}  # vendredi le plus froid
    couleurs = estimer(HISTORIQUE, semaine, rigueur=rigueur, climatologie=CLIMATOLOGIE)
    rouges = [j for j in semaine if couleurs.couleur(j) == ROUGE]
    assert rouges
    assert rouges == semaine[-len(rouges) :]


def test_couleur_inconnue():
    with pytest.raises(CouleurInconnue, match="2031-01-01"):
        CouleursTempo({}).couleur(date(2031, 1, 1))


# --- Calendrier et coût -------------------------------------------------------------------

GRILLE_6 = Grilles.charger("tempo")


def test_grille_cre_tempo():
    grille = GRILLE_6.en_vigueur(6, date(2026, 10, 19))
    assert set(grille.prix) == POSTES_TEMPO
    assert grille.prix["hc_bleu"] == Decimal("0.1356")
    assert grille.prix["hp_rouge"] == Decimal("0.7295")
    with pytest.raises(TarifIntrouvable):
        GRILLE_6.en_vigueur(3, date(2026, 10, 19))  # Tempo à partir de 6 kVA


def test_calendrier_tempo_6h_a_6h():
    """Vendredi 17/01/2025 rouge, samedi 18 blanc : la nuit du samedi (0h-6h) reste rouge."""
    calendrier = calendrier_pour(POSTES_TEMPO, PLAGES, CouleursTempo(HISTORIQUE))
    assert isinstance(calendrier, CalendrierTempo)
    un = Decimal(1)
    assert calendrier.repartir(datetime(2025, 1, 17, 10), un) == {"hp_rouge": un}
    assert calendrier.repartir(datetime(2025, 1, 17, 22), un) == {"hc_rouge": un}
    assert calendrier.repartir(datetime(2025, 1, 18, 3), un) == {"hc_rouge": un}
    assert calendrier.repartir(datetime(2025, 1, 18, 6), un) == {"hp_blanc": un}
    assert calendrier.repartir(datetime(2025, 1, 18, 21), un) == {"hp_blanc": un}
    # Les plages du compteur (02:00-07:00) ne comptent pas : 6h est en heures pleines Tempo.
    assert calendrier.repartir(datetime(2025, 1, 19, 6), un) == {"hp_bleu": un}


def test_tempo_sans_couleurs():
    with pytest.raises(DonneesManquantes, match="couleurs"):
        calendrier_pour(POSTES_TEMPO, PLAGES)


def test_cout_tempo_sur_un_jour_rouge():
    """Vendredi 17/01/2025, 1 kWh par heure : 16 h pleines et 6 h creuses rouges, 2 h creuses de la veille."""
    conso = [(datetime(2025, 1, 17, h), 1.0) for h in range(24)]
    cout = cout_option("tempo", GRILLE_6, 6, conso, couleurs=CouleursTempo(HISTORIQUE))
    assert cout.kwh == {
        "hc_rouge": Decimal(8),
        "hp_rouge": Decimal(16),
    }  # la veille (jeudi 16) est rouge aussi
    grille = GRILLE_6.en_vigueur(6, date(2025, 1, 17))
    assert cout.energie == 8 * grille.prix["hc_rouge"] + 16 * grille.prix["hp_rouge"]
    assert "jours_couleur_estimee" not in cout.arrondi()


def test_cout_tempo_jours_estimes_signales():
    conso = [(datetime(2031, 1, 13, h), 1.0) for h in range(24)]
    couleurs = estimer(HISTORIQUE, jours_utiles([date(2031, 1, 13)]), climatologie=CLIMATOLOGIE)
    grilles = Grilles(
        [Grille("tempo", 6, date(2030, 1, 1), None, Decimal(365), dict.fromkeys(POSTES_TEMPO, Decimal(1)))]
    )
    cout = cout_option("tempo", grilles, 6, conso, couleurs=couleurs)
    assert cout.jours_estimes == {date(2031, 1, 12), date(2031, 1, 13)}
    assert cout.arrondi()["jours_couleur_estimee"] == 2


def test_comparer_tempo_indisponible_sans_couleur():
    """Un jour sans couleur (ni réelle ni estimée) : Tempo mis de côté avec la raison, pas d'erreur."""
    grilles = {"tempo": GRILLE_6}
    conso = [(datetime(2026, 10, 19, 12), 1.0)]
    comp = comparer(grilles, 6, conso, PLAGES, "tempo", couleurs=CouleursTempo({}))
    assert comp.indisponibles == {"tempo": "couleur Tempo inconnue le 2026-10-19"}
    sans = comparer(grilles, 6, conso, PLAGES, "tempo")
    assert sans.indisponibles == {"tempo": "l'option Tempo demande les couleurs des jours"}
