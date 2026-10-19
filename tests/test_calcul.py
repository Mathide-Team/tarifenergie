"""Moteur : heures creuses, prix du jour, abonnement au jour, classement."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from custom_components.tarifenergie.calcul import (
    PlagesHC,
    PlagesInvalides,
    comparer,
    cout_option,
    heures_locales,
)
from custom_components.tarifenergie.modele import Grille, Grilles


def _grilles(option: str, prix: dict[str, str], abonnement: str = "365") -> Grilles:
    """Deux grilles fictives : prix doublés à partir du 01/08/2026."""
    p1 = {k: Decimal(v) for k, v in prix.items()}
    p2 = {k: v * 2 for k, v in p1.items()}
    return Grilles(
        [
            Grille(option, 6, date(2026, 1, 1), date(2026, 7, 31), Decimal(abonnement), p1),
            Grille(option, 6, date(2026, 8, 1), None, Decimal(abonnement) * 2, p2),
        ]
    )


class TestPlages:
    def test_lecture_et_minuit(self):
        p = PlagesHC.lire("22:00-06:00")
        assert p.minutes_par_jour() == 8 * 60
        assert [p.fraction_hc(h) for h in (21, 22, 23, 0, 5, 6)] == [0, 1, 1, 1, 1, 0]
        assert p.texte() == "22:00-06:00"

    def test_demi_heures_et_plusieurs_plages(self):
        p = PlagesHC.lire("23h30-07h30 ; 13:00-14:00")
        assert p.fraction_hc(23) == Decimal("0.5")
        assert p.fraction_hc(7) == Decimal("0.5")
        assert p.fraction_hc(13) == 1
        assert p.minutes_par_jour() == 9 * 60
        assert p.texte() == "23:30-07:30, 13:00-14:00"

    def test_jusqu_a_minuit(self):
        p = PlagesHC.lire("20:00-24:00, 00:00-04:00")
        assert p.minutes_par_jour() == 8 * 60
        assert p.fraction_hc(23) == 1

    @pytest.mark.parametrize(
        "texte",
        [
            "",
            " , ",
            "22-06",
            "25:00-06:00",
            "22:00-24:30",
            "22:61-06:00",
            "06:00-06:00",
            "00:00-24:00",
            "22:00-06:00, 23:00-01:00",
            "01:00-03:00, 02:00-04:00",
        ],
    )
    def test_refus(self, texte):
        with pytest.raises(PlagesInvalides):
            PlagesHC.lire(texte)


def test_base_prix_du_jour_et_abonnement():
    grilles = _grilles("base", {"base": "0.10"})
    conso = [(datetime(2026, 7, 31, 12), 10.0), (datetime(2026, 8, 1, 12), 10.0)]
    cout = cout_option("base", grilles, 6, conso)
    # 10 kWh à 0,10 puis 10 kWh à 0,20 ; abonnement 365 €/an puis 730 €/an : 1 € + 2 €.
    assert cout.energie == Decimal("3.00")
    assert cout.abonnement == Decimal(3)
    assert cout.total == Decimal("6.00")
    assert cout.kwh == {"base": Decimal(20)}
    assert cout.arrondi()["grilles"] == ["2026-01-01", "2026-08-01"]


def test_hphc_repartition_au_prorata():
    grilles = _grilles("hphc", {"hp": "0.20", "hc": "0.10"})
    plages = PlagesHC.lire("23:30-07:30")
    conso = [(datetime(2026, 3, 1, 23), 2.0), (datetime(2026, 3, 1, 12), 1.0), (datetime(2026, 3, 1, 3), 0.0)]
    cout = cout_option("hphc", grilles, 6, conso, plages)
    assert cout.kwh == {"hc": Decimal(1), "hp": Decimal(2)}
    assert cout.energie == Decimal("0.50")
    assert cout.abonnement == Decimal(1)  # un seul jour


def test_annee_bissextile():
    grilles = Grilles([Grille("base", 6, date(2028, 1, 1), None, Decimal(366), {"base": Decimal(0)})])
    assert cout_option("base", grilles, 6, [(datetime(2028, 2, 29), 1.0)]).abonnement == 1


def test_hphc_sans_plages():
    with pytest.raises(ValueError, match="plages"):
        cout_option("hphc", _grilles("hphc", {"hp": "1", "hc": "1"}), 6, [])


def test_comparer_classement_et_economie():
    grilles = {
        "base": _grilles("base", {"base": "0.15"}),
        "hphc": _grilles("hphc", {"hp": "0.20", "hc": "0.10"}),
    }
    plages = PlagesHC.lire("22:00-06:00")
    # Toute la consommation la nuit : Heures creuses gagne.
    conso = [(h, 1.0) for h in heures_locales(datetime(2026, 3, 1), datetime(2026, 3, 3)) if h.hour < 6]
    comp = comparer(grilles, 6, conso, plages, "base")
    assert comp.jours == 2
    assert comp.moins_chere.option == "hphc"
    assert [c.option for c in comp.classement] == ["hphc", "base"]
    assert comp.economie == comp.couts["base"].total - comp.couts["hphc"].total == Decimal("0.60")
    assert comparer(grilles, 6, conso, plages, "hphc").economie == 0


def test_comparer_option_indisponible():
    grilles = {"base": Grilles([]), "hphc": _grilles("hphc", {"hp": "0.2", "hc": "0.1"})}
    comp = comparer(grilles, 6, [(datetime(2026, 3, 1, 1), 1.0)], PlagesHC.lire("22:00-06:00"), "base")
    assert set(comp.couts) == {"hphc"}
    assert "6 kVA" in comp.indisponibles["base"]
    assert comp.economie is None
    vide = comparer(grilles, 6, [], PlagesHC.lire("22:00-06:00"), "hphc")
    assert vide.jours == 0 and vide.couts["hphc"].total == 0


def test_cas_reel_une_annee_constante():
    """1 kWh par heure pendant un an, 6 kVA, grilles réelles : ordre de grandeur vérifié à la main."""
    grilles = {"base": Grilles.charger("base"), "hphc": Grilles.charger("hphc")}
    debut = datetime(2025, 10, 18)
    conso = [(h, 1.0) for h in heures_locales(debut, debut + timedelta(days=365))]
    comp = comparer(grilles, 6, conso, PlagesHC.lire("22:00-06:00"), "base")
    base = comp.couts["base"]
    assert base.kwh["base"] == 8760
    # Prix du kWh entre 0,1940 et 0,2001 € TTC, abonnement entre 185,94 et 190,81 €/an.
    assert Decimal(8760) * Decimal("0.1940") + Decimal("185.94") < base.total
    assert base.total < Decimal(8760) * Decimal("0.2001") + Decimal("190.81")
    assert comp.couts["hphc"].kwh["hc"] == 8760 / 3
