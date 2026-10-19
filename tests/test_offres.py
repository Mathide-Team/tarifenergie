"""Offres de marché (issues #5 et #6) : lecture des YAML livrés, validation, comparaison."""

from datetime import datetime
from decimal import Decimal

import pytest

from custom_components.tarifenergie.calcul import PlagesHC, comparer, cout_option
from custom_components.tarifenergie.modele import Grilles
from custom_components.tarifenergie.offres import (
    OffreInvalide,
    grilles_offres,
    lire_offres,
    offre_depuis_dict,
)

UN_JOUR = [(datetime(2026, 10, 19, 14, 0), 1.0)]  # 1 kWh, hors heures creuses
DIX_KWH = [(datetime(2026, 10, 19, 14, 0), 10.0)]  # 10 kWh un jour, hors heures creuses
PLAGES = PlagesHC.lire("22:00-06:00")


@pytest.fixture(scope="module")
def offres():
    return lire_offres()


def test_quatre_offres_livrees(offres):
    assert sorted(offres) == [
        "alterna_fixe_1an",
        "la_bellenergie_garance",
        "la_bellenergie_prudence",
        "ohm_serente_fixe_1an",
    ]
    assert all(o.grilles["base"] for o in offres.values())


def test_prudence_grille_du_1er_aout_2026(offres):
    """Grille TTC du 01/08/2026 (issue #64) : 6 kVA, abonnement 15,36 €/mois, 19,68 c€ Base."""
    grilles = grilles_offres(offres)
    g = grilles["la_bellenergie_prudence:base"].en_vigueur(6, datetime(2026, 10, 19).date())
    assert (g.debut, g.abonnement_an, g.prix) == (
        datetime(2026, 8, 1).date(),
        Decimal("184.32"),  # 15,36 € TTC/mois x 12
        {"base": Decimal("0.1968")},
    )
    g = grilles["la_bellenergie_prudence:hphc"].en_vigueur(6, datetime(2026, 10, 19).date())
    assert g.abonnement_an == Decimal("184.32")
    assert g.prix == {"hp": Decimal("0.2106"), "hc": Decimal("0.1565")}


def test_garance_abonnements_3_ans(offres):
    """Grille du 01/08/2026 (issue #63) : 6 kVA Base 20,36 €/mois, HC 9 kVA 24,66 €/mois."""
    grilles = grilles_offres(offres)
    g = grilles["la_bellenergie_garance:base"].en_vigueur(6, datetime(2026, 10, 19).date())
    assert g.abonnement_an == Decimal("244.32")  # 20,36 x 12
    assert g.prix["base"] == Decimal("0.1968")
    g = grilles["la_bellenergie_garance:hphc"].en_vigueur(9, datetime(2026, 10, 19).date())
    assert g.abonnement_an == Decimal("295.92")  # 24,66 x 12


def test_ohm_grille_du_14_octobre_2026(offres):
    """Grille du 14/10/2026 (issue #40) : 6 kVA Base 14,45 €/mois, 21,83 c€ ; HC 14,64 €/mois."""
    grilles = grilles_offres(offres)
    g = grilles["ohm_serente_fixe_1an:base"].en_vigueur(6, datetime(2026, 10, 19).date())
    assert g.debut == datetime(2026, 10, 14).date()
    assert g.abonnement_an == Decimal("173.40")  # 14,45 x 12
    assert g.prix["base"] == Decimal("0.2183")
    assert grilles["ohm_serente_fixe_1an:base"].en_vigueur(3, datetime(2026, 10, 19).date()).prix == {
        "base": Decimal("0.2001")
    }
    g = grilles["ohm_serente_fixe_1an:hphc"].en_vigueur(6, datetime(2026, 10, 19).date())
    assert g.abonnement_an == Decimal("175.68")  # 14,64 x 12
    assert g.prix == {"hp": Decimal("0.2347"), "hc": Decimal("0.1723")}


def test_alterna_hc_des_3_kva(offres):
    """Grille du 01/09/2026 (issue #44) : HC dès 3 kVA, 6 kVA Base 17,66 €/mois, 19,19 c€."""
    grilles = grilles_offres(offres)
    g = grilles["alterna_fixe_1an:hphc"].en_vigueur(3, datetime(2026, 10, 19).date())
    assert g.abonnement_an == Decimal("167.16")  # 13,93 x 12
    assert g.prix == {"hp": Decimal("0.2054"), "hc": Decimal("0.1528")}
    g = grilles["alterna_fixe_1an:base"].en_vigueur(6, datetime(2026, 10, 19).date())
    assert g.abonnement_an == Decimal("211.92")  # 17,66 x 12
    assert g.prix["base"] == Decimal("0.1919")


def test_cles_de_comparaison_composites(offres):
    cles = grilles_offres(offres)
    assert "la_bellenergie_prudence:base" in cles
    assert "la_bellenergie_prudence:hphc" in cles
    assert all(isinstance(g, Grilles) for g in cles.values())


def test_cout_option_prudence_sur_un_kwh(offres):
    """1 kWh un jour : abonnement au prorata (184,32 €/an ÷ 365) + 19,68 c€."""
    grilles = grilles_offres(offres)
    cout = cout_option(
        "la_bellenergie_prudence:base", grilles["la_bellenergie_prudence:base"], 6, UN_JOUR, PLAGES
    )
    assert cout.total == (Decimal("184.32") / Decimal("365") + Decimal("0.1968")).quantize(Decimal("0.01"))


def test_comparaison_trv_contre_offres(offres):
    """Le classement mélange TRV et offres.

    Avec 10 kWh dans la journée, Prudence Base (19,68 c€, 184,32 €/an) bat le TRV Base
    (20,01 c€, 190,81 €/an), Ohm (21,83 c€) et Alterna (19,19 c€ mais 211,92 €/an).
    À 1 kWh seulement, l'abonnement domine et Ohm (173,40 €/an) gagnerait.
    """
    from custom_components.tarifenergie.const import OPTIONS
    from custom_components.tarifenergie.modele import Grilles as GrillesTRV

    grilles = {option: GrillesTRV.charger(option) for option in OPTIONS}
    grilles.update(grilles_offres(offres))
    comp = comparer(grilles, 6, DIX_KWH, PLAGES, "base")
    assert comp.moins_chere.option == "la_bellenergie_prudence:base"
    trv = comp.couts["base"]
    prudence = comp.couts["la_bellenergie_prudence:base"]
    assert comp.economie == (trv.total - prudence.total).quantize(Decimal("0.01"))
    # Puissance non proposée par l'offre : indisponible, avec la raison.
    comp3 = comparer(grilles, 3, DIX_KWH, PLAGES, "base")
    assert "la_bellenergie_prudence:hphc" in comp3.indisponibles


@pytest.mark.parametrize(
    ("donnees", "chemin_fautif"),
    [
        ({"id": "autre", "type_prix": "fixe"}, "offre.id"),
        ({"id": "x", "type_prix": "indexe"}, "offre.type_prix"),
        (
            {
                "id": "x",
                "type_prix": "fixe",
                "grille_du": "2026-08-01",
                "duree_fixite_mois": 12,
                "source": "https://exemple.fr",
                "fournisseur": "F",
                "offre": "O",
                "options": {"base": {"abonnement_mensuel_ttc": {42: 11.0}, "kwh_ttc": {"base": 0.2}}},
            },
            "abonnement_mensuel_ttc",
        ),
        (
            {
                "id": "x",
                "type_prix": "fixe",
                "grille_du": "2026-08-01",
                "duree_fixite_mois": 12,
                "source": "https://exemple.fr",
                "fournisseur": "F",
                "offre": "O",
                "options": {"hphc": {"abonnement_mensuel_ttc": {6: 15.0}, "kwh_ttc": {"hp": 0.2}}},
            },
            "offre.options",
        ),
    ],
)
def test_offres_invalides(donnees, chemin_fautif):
    if isinstance(donnees.get("grille_du"), str):
        from datetime import date

        donnees["grille_du"] = date.fromisoformat(donnees["grille_du"])
    with pytest.raises(OffreInvalide, match=chemin_fautif):
        offre_depuis_dict(donnees, "x")
