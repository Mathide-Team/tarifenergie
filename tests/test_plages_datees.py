"""Plages HC du compteur qui changent en cours d'année (#369)."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from custom_components.tarifenergie.calcul import comparer, cout_option
from custom_components.tarifenergie.calendrier import (
    CalendrierHPHC,
    PlagesDatees,
    PlagesHC,
    PlagesInvalides,
    calendrier_pour,
)
from custom_components.tarifenergie.modele import Grille, Grilles

AVANT = "22:00-06:00"
APRES = "02:00-07:00, 13:00-16:00"
CHANGEMENT = date(2026, 3, 15)
TEXTE = f"{AVANT} | 2026-03-15: {APRES}"
UN = Decimal(1)


def test_lecture_et_texte():
    plages = PlagesDatees.lire(TEXTE)
    assert plages.periodes == ((None, PlagesHC.lire(AVANT)), (CHANGEMENT, PlagesHC.lire(APRES)))
    assert plages.texte() == TEXTE
    assert PlagesDatees.lire(plages.texte()) == plages


def test_un_seul_jeu_de_plages_compatible():
    """La saisie d'avant #369 reste valable : mêmes plages sur toute la fenêtre."""
    plages = PlagesDatees.lire(AVANT)
    assert plages == PlagesDatees.uniques(PlagesHC.lire(AVANT))
    assert plages.du_jour(date(2020, 1, 1)) == plages.du_jour(date(2030, 1, 1)) == PlagesHC.lire(AVANT)
    assert plages.texte() == AVANT


def test_plages_du_jour():
    plages = PlagesDatees.lire(f"{TEXTE} | 2026-09-01: 23:00-07:00")
    assert plages.du_jour(date(2026, 3, 14)).texte() == AVANT
    assert plages.du_jour(CHANGEMENT).texte() == APRES  # le jour du changement : nouvelles plages
    assert plages.du_jour(date(2026, 8, 31)).texte() == APRES
    assert plages.du_jour(date(2026, 9, 1)).texte() == "23:00-07:00"
    assert [p["depuis"] for p in plages.resume()] == [None, "2026-03-15", "2026-09-01"]
    assert plages.resume([2]) == [{"depuis": "2026-09-01", "plages": "23:00-07:00"}]


@pytest.mark.parametrize(
    ("texte", "message"),
    [
        ("2026-03-15: 22:00-06:00", "première période"),
        ("22:00-06:00 | 02:00-07:00", "changement sans date"),
        ("22:00-06:00 | 2026-02-30: 02:00-07:00", "date illisible"),
        ("22:00-06:00 | 2026-03-15: 02:00-07:00 | 2026-03-15: 23:00-07:00", "non croissantes"),
        ("22:00-06:00 | 2026-03-15: 02:00-07:00 | 2026-01-01: 23:00-07:00", "non croissantes"),
        ("22:00-06:00 | 2026-03-15: ", "aucune plage"),
        ("22:00-06:00 | 2026-03-15: 25:00-07:00", "heure impossible"),
    ],
)
def test_saisies_refusees(texte, message):
    with pytest.raises(PlagesInvalides, match=message):
        PlagesDatees.lire(texte)


def test_heure_valorisee_selon_les_plages_du_jour():
    """23h : creuse avant le 15 mars (22h-6h), pleine après (2h-7h, 13h-16h)."""
    calendrier = calendrier_pour({"hp", "hc"}, PlagesDatees.lire(TEXTE))
    assert isinstance(calendrier, CalendrierHPHC)
    assert calendrier.repartir(datetime(2026, 3, 14, 23), UN) == {"hc": UN, "hp": 0}
    assert calendrier.repartir(datetime(2026, 3, 15, 23), UN) == {"hc": 0, "hp": UN}
    assert calendrier.repartir(datetime(2026, 3, 15, 14), UN) == {"hc": UN, "hp": 0}
    # Plages simples : converties en une seule période.
    simple = calendrier_pour({"hp", "hc"}, PlagesHC.lire(AVANT))
    assert simple.plages == PlagesDatees.uniques(PlagesHC.lire(AVANT))


GRILLES = Grilles(
    [Grille("hphc", 6, date(2026, 1, 1), None, Decimal(0), {"hp": Decimal(2), "hc": Decimal(1)})]
)


def test_cout_et_periodes_appliquees():
    conso = [(datetime(2026, 3, 14, 23), 1.0), (datetime(2026, 3, 15, 23), 1.0)]
    cout = cout_option("hphc", GRILLES, 6, conso, PlagesDatees.lire(TEXTE))
    assert cout.kwh == {"hc": UN, "hp": UN}
    assert cout.energie == Decimal(3)
    assert cout.arrondi()["plages_hc"] == [
        {"depuis": None, "plages": AVANT},
        {"depuis": "2026-03-15", "plages": APRES},
    ]
    # Fenêtre après le changement : seule la période appliquée est exposée.
    apres = cout_option("hphc", GRILLES, 6, conso[1:], PlagesDatees.lire(TEXTE))
    assert apres.plages_hc == [{"depuis": "2026-03-15", "plages": APRES}]


def test_comparer_avec_changement():
    conso = [(datetime(2026, 3, 14, 23), 1.0), (datetime(2026, 3, 15, 23), 1.0)]
    comp = comparer({"hphc": GRILLES}, 6, conso, PlagesDatees.lire(TEXTE), "hphc")
    assert comp.couts["hphc"].total == Decimal(3)
    sans = cout_option("hphc", GRILLES, 6, conso, PlagesHC.lire(AVANT))
    assert sans.energie == Decimal(2)  # sans le changement, les deux heures seraient creuses
    assert "plages_hc" in sans.arrondi()


# --- Plages saisonnières été / hiver (#368) -----------------------------------------------

SAISONS = "été 02:00-07:00, 13:00-16:00 / hiver 23:00-07:00"


def test_saisons_lecture_et_bascules():
    from custom_components.tarifenergie.calendrier import PlagesSaisonnieres, est_hiver

    plages = PlagesDatees.lire(SAISONS)
    saison = plages.periodes[0][1]
    assert saison == PlagesSaisonnieres(PlagesHC.lire(APRES), PlagesHC.lire("23:00-07:00"))
    assert plages.texte() == SAISONS
    # Ordre libre, sans accent, deux-points facultatifs, en anglais.
    assert PlagesDatees.lire("hiver: 23:00-07:00 / ete 02:00-07:00,13:00-16:00") == plages
    assert PlagesDatees.lire("winter 23:00-07:00 / summer 02:00-07:00, 13:00-16:00") == plages
    for jour, hiver in (
        (date(2026, 3, 31), True),
        (date(2026, 4, 1), False),
        (date(2026, 10, 31), False),
        (date(2026, 11, 1), True),
        (date(2027, 1, 15), True),
    ):
        assert est_hiver(jour) is hiver
        assert plages.du_jour(jour).texte() == ("23:00-07:00" if hiver else APRES)


@pytest.mark.parametrize(
    ("texte", "message"),
    [
        ("été 02:00-07:00", "il faut l'été et l'hiver"),
        ("été 02:00-07:00 / été 23:00-07:00", "saison en double"),
        ("printemps 02:00-07:00 / hiver 23:00-07:00", "saison attendue"),
        ("été 02:00-07:00 / hiver", "aucune plage"),
    ],
)
def test_saisons_refusees(texte, message):
    with pytest.raises(PlagesInvalides, match=message):
        PlagesDatees.lire(texte)


def test_changement_vers_des_plages_saisonnieres():
    """Redéploiement Enedis : 22h-6h jusqu'au 31 octobre 2026, puis plages été / hiver."""
    plages = PlagesDatees.lire(f"22:00-06:00 | 2026-11-01: {SAISONS}")
    assert plages.du_jour(date(2026, 10, 31)).texte() == "22:00-06:00"
    assert plages.du_jour(date(2026, 11, 1)).texte() == "23:00-07:00"
    assert plages.du_jour(date(2027, 4, 1)).texte() == APRES
    assert plages.resume([1]) == [{"depuis": "2026-11-01", "plages": SAISONS}]
    calendrier = calendrier_pour({"hp", "hc"}, plages)
    assert calendrier.repartir(datetime(2027, 1, 10, 6), UN) == {"hc": UN, "hp": 0}  # hiver : 23h-7h
    assert calendrier.repartir(datetime(2027, 6, 10, 6), UN) == {"hc": UN, "hp": 0}  # été : 2h-7h
    assert calendrier.repartir(datetime(2027, 6, 10, 14), UN) == {"hc": UN, "hp": 0}
    assert calendrier.repartir(datetime(2027, 1, 10, 14), UN) == {"hc": 0, "hp": UN}
