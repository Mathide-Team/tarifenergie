"""Calendriers tarifaires (#339) : un calendrier par offre-option, déduit des postes de sa grille."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from custom_components.tarifenergie.calcul import comparer
from custom_components.tarifenergie.calendrier import (
    CalendrierBase,
    CalendrierHPHC,
    PlagesHC,
    PostesNonPrisEnCharge,
    calendrier_pour,
)
from custom_components.tarifenergie.modele import Grille, Grilles

PLAGES = PlagesHC.lire("23:30-07:30")


def test_base():
    calendrier = calendrier_pour({"base"}, None)
    assert isinstance(calendrier, CalendrierBase)
    assert calendrier.repartir(datetime(2026, 10, 19, 14), Decimal(2)) == {"base": Decimal(2)}


def test_hphc_prorata_des_minutes():
    """23:00-24:00 avec des HC à partir de 23:30 : moitié HC, moitié HP ; la somme est conservée."""
    calendrier = calendrier_pour({"hp", "hc"}, PLAGES)
    assert isinstance(calendrier, CalendrierHPHC)
    parts = calendrier.repartir(datetime(2026, 10, 19, 23), Decimal(2))
    assert parts == {"hc": Decimal(1), "hp": Decimal(1)}
    assert sum(calendrier.repartir(datetime(2026, 10, 19, 7), Decimal("0.7")).values()) == Decimal("0.7")


def test_hphc_sans_plages():
    with pytest.raises(ValueError, match="plages"):
        calendrier_pour({"hp", "hc"}, None)


def test_structure_pas_encore_prise_en_charge():
    """Tempo, heures super creuses, week-end (#340 à #342) : refus explicite, pas de calcul faux."""
    with pytest.raises(PostesNonPrisEnCharge, match="hc, hp, hsc"):
        calendrier_pour({"hp", "hc", "hsc"}, PLAGES)


def test_offre_option_non_prise_en_charge_mise_de_cote():
    """Une offre-option à 3 postes est indisponible avec la raison ; les autres restent comparées."""
    prix_hsc = {"hp": Decimal("0.25"), "hc": Decimal("0.18"), "hsc": Decimal("0.12")}
    grilles = {
        "base": Grilles([Grille("base", 6, date(2026, 1, 1), None, Decimal(365), {"base": Decimal("0.2")})]),
        "x_hsc": Grilles([Grille("x_hsc", 6, date(2026, 1, 1), None, Decimal(365), prix_hsc)]),
    }
    comp = comparer(grilles, 6, [(datetime(2026, 10, 19, 14), 1.0)], PLAGES, "base")
    assert sorted(comp.couts) == ["base"]
    assert comp.indisponibles == {"x_hsc": "postes non pris en charge : hc, hp, hsc"}
