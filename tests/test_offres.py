"""Offres de marché (issues #5, #6 et #343) : une offre-option par fichier, validation, comparaison."""

from datetime import date, datetime
from decimal import Decimal

import pytest
import yaml

from custom_components.tarifenergie.calcul import PlagesHC, comparer, cout_option
from custom_components.tarifenergie.modele import Grilles
from custom_components.tarifenergie.offres import (
    OffreInvalide,
    charger_offre,
    exclusions,
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


# Inventaire #6 : une offre-option = une issue = un fichier (#343).
ISSUES_PAR_OFFRE_OPTION = {
    "alterna_du_coin_1an_base": 43,
    "alterna_du_coin_1an_hphc": 151,
    "alterna_fixe_1an_base": 44,
    "alterna_fixe_1an_hphc": 152,
    "geg_elec_verte_3ans_base": 56,
    "geg_elec_verte_3ans_hphc": 137,
    "ilek_enrfixe_plus_base": 57,
    "ilek_enrfixe_plus_hphc": 158,
    "la_bellenergie_constance_base": 62,
    "la_bellenergie_constance_hphc": 164,
    "la_bellenergie_garance_base": 63,
    "la_bellenergie_garance_hphc": 165,
    "la_bellenergie_prudence_base": 64,
    "la_bellenergie_prudence_hphc": 166,
    "ohm_fixe_2ans_base": 38,
    "ohm_fixe_2ans_hphc": 146,
    "ohm_serente_fixe_1an_base": 40,
    "ohm_serente_fixe_1an_hphc": 148,
    "plenitude_pleniweb_1an_base": 65,
    "plenitude_pleniweb_1an_hphc": 167,
    "primeo_fixe_confort_base": 61,
    "primeo_fixe_confort_hphc": 163,
    "selia_elec_vert_fixe_base": 68,
    "selia_elec_vert_fixe_hphc": 170,
}


def test_une_offre_option_par_fichier(offres):
    """24 offres-options livrées, chacune avec son issue, une seule option par fichier."""
    assert {ident: o.issue for ident, o in offres.items()} == ISSUES_PAR_OFFRE_OPTION
    for ident, offre in offres.items():
        assert ident.endswith(f"_{offre.option}")
        assert offre.territoire == "enedis"
        assert offre.grilles.puissances()


def test_prudence_grille_du_1er_aout_2026(offres):
    """Grille TTC du 01/08/2026 (issue #64) : 6 kVA, abonnement 15,36 €/mois, 19,68 c€ Base."""
    grilles = grilles_offres(offres)
    g = grilles["la_bellenergie_prudence_base"].en_vigueur(6, datetime(2026, 10, 19).date())
    assert (g.debut, g.abonnement_an, g.prix) == (
        datetime(2026, 8, 1).date(),
        Decimal("184.32"),  # 15,36 € TTC/mois x 12
        {"base": Decimal("0.1968")},
    )
    g = grilles["la_bellenergie_prudence_hphc"].en_vigueur(6, datetime(2026, 10, 19).date())
    assert g.abonnement_an == Decimal("184.32")
    assert g.prix == {"hp": Decimal("0.2106"), "hc": Decimal("0.1565")}


def test_garance_abonnements_3_ans(offres):
    """Grille du 01/08/2026 (issue #63) : 6 kVA Base 20,36 €/mois, HC 9 kVA 24,66 €/mois."""
    grilles = grilles_offres(offres)
    g = grilles["la_bellenergie_garance_base"].en_vigueur(6, datetime(2026, 10, 19).date())
    assert g.abonnement_an == Decimal("244.32")  # 20,36 x 12
    assert g.prix["base"] == Decimal("0.1968")
    g = grilles["la_bellenergie_garance_hphc"].en_vigueur(9, datetime(2026, 10, 19).date())
    assert g.abonnement_an == Decimal("295.92")  # 24,66 x 12


def test_ohm_grille_du_14_octobre_2026(offres):
    """Grille du 14/10/2026 (issue #40) : 6 kVA Base 14,45 €/mois, 21,83 c€ ; HC 14,64 €/mois."""
    grilles = grilles_offres(offres)
    g = grilles["ohm_serente_fixe_1an_base"].en_vigueur(6, datetime(2026, 10, 19).date())
    assert g.debut == datetime(2026, 10, 14).date()
    assert g.abonnement_an == Decimal("173.40")  # 14,45 x 12
    assert g.prix["base"] == Decimal("0.2183")
    assert grilles["ohm_serente_fixe_1an_base"].en_vigueur(3, datetime(2026, 10, 19).date()).prix == {
        "base": Decimal("0.2001")
    }
    g = grilles["ohm_serente_fixe_1an_hphc"].en_vigueur(6, datetime(2026, 10, 19).date())
    assert g.abonnement_an == Decimal("175.68")  # 14,64 x 12
    assert g.prix == {"hp": Decimal("0.2347"), "hc": Decimal("0.1723")}


def test_alterna_hc_des_3_kva(offres):
    """Grille du 01/09/2026 (issue #44) : HC dès 3 kVA, 6 kVA Base 17,66 €/mois, 19,19 c€."""
    grilles = grilles_offres(offres)
    g = grilles["alterna_fixe_1an_hphc"].en_vigueur(3, datetime(2026, 10, 19).date())
    assert g.abonnement_an == Decimal("167.16")  # 13,93 x 12
    assert g.prix == {"hp": Decimal("0.2054"), "hc": Decimal("0.1528")}
    g = grilles["alterna_fixe_1an_base"].en_vigueur(6, datetime(2026, 10, 19).date())
    assert g.abonnement_an == Decimal("211.92")  # 17,66 x 12
    assert g.prix["base"] == Decimal("0.1919")


def test_lot_2_offres_fixes(offres):
    """Lot 2 (issues #38, #43, #56, #57, #61, #62, #65, #68) : valeurs citées des grilles."""
    grilles = grilles_offres(offres)
    jour = datetime(2026, 10, 19).date()

    # Ohm Fixe 2 ans, grille du 16/10/2026 (#38) : 6 kVA 15,88 €/mois, 22,49 c€.
    g = grilles["ohm_fixe_2ans_base"].en_vigueur(6, jour)
    assert (g.debut, g.abonnement_an, g.prix["base"]) == (
        datetime(2026, 10, 16).date(),
        Decimal("190.56"),  # 15,88 x 12
        Decimal("0.2249"),
    )
    g = grilles["ohm_fixe_2ans_hphc"].en_vigueur(6, jour)
    assert g.prix == {"hp": Decimal("0.2421"), "hc": Decimal("0.1771")}

    # Alterna du coin 1 an, grille du 01/09/2026 (#43) : 6 kVA 17,66 €/mois, 19,68 c€.
    g = grilles["alterna_du_coin_1an_base"].en_vigueur(6, jour)
    assert g.abonnement_an == Decimal("211.92")  # 17,66 x 12
    assert g.prix["base"] == Decimal("0.1968")
    g = grilles["alterna_du_coin_1an_hphc"].en_vigueur(3, jour)  # HC dès 3 kVA
    assert g.abonnement_an == Decimal("167.16")  # 13,93 x 12
    assert g.prix == {"hp": Decimal("0.2107"), "hc": Decimal("0.1565")}

    # GEG fixe 3 ans, grille du 05/10/2026 (#56) : kWh HC/HP selon la puissance.
    g = grilles["geg_elec_verte_3ans_hphc"].en_vigueur(6, jour)
    assert g.prix == {"hp": Decimal("0.1983"), "hc": Decimal("0.1584")}
    g = grilles["geg_elec_verte_3ans_hphc"].en_vigueur(12, jour)
    assert g.prix == {"hp": Decimal("0.2014"), "hc": Decimal("0.1584")}
    g = grilles["geg_elec_verte_3ans_hphc"].en_vigueur(18, jour)
    assert g.prix == {"hp": Decimal("0.2014"), "hc": Decimal("0.1656")}
    g = grilles["geg_elec_verte_3ans_base"].en_vigueur(3, jour)
    assert g.prix["base"] == Decimal("0.1837")

    # ilek ÉnRFixe+, grille d'octobre 2026 (#57) : 6 kVA 25,10 €/mois, 24,00 c€.
    g = grilles["ilek_enrfixe_plus_base"].en_vigueur(6, jour)
    assert g.abonnement_an == Decimal("301.20")  # 25,10 x 12
    assert g.prix["base"] == Decimal("0.2400")

    # Primeo Fixe Confort, grille du 01/08/2026 (#61) : 6 kVA 20,16 €/mois, 16,74 c€.
    g = grilles["primeo_fixe_confort_base"].en_vigueur(6, jour)
    assert g.abonnement_an == Decimal("241.92")  # 20,16 x 12
    assert g.prix["base"] == Decimal("0.1674")
    g = grilles["primeo_fixe_confort_hphc"].en_vigueur(6, jour)
    assert g.prix == {"hp": Decimal("0.1787"), "hc": Decimal("0.1344")}

    # la bellenergie Constance, grille du 01/08/2026 (#62) : 6 kVA 17,87 €/mois.
    g = grilles["la_bellenergie_constance_base"].en_vigueur(6, jour)
    assert g.abonnement_an == Decimal("214.44")  # 17,87 x 12
    assert g.prix["base"] == Decimal("0.1968")
    g = grilles["la_bellenergie_constance_hphc"].en_vigueur(9, jour)
    assert g.abonnement_an == Decimal("266.04")  # 22,17 x 12

    # Plenitude Pleniweb 1 an, grille du 01/10/2026 (#65) : 6 kVA 18,26 €/mois, 18,37 c€.
    g = grilles["plenitude_pleniweb_1an_base"].en_vigueur(6, jour)
    assert g.abonnement_an == Decimal("219.12")  # 18,26 x 12
    assert g.prix["base"] == Decimal("0.1837")
    g = grilles["plenitude_pleniweb_1an_hphc"].en_vigueur(3, jour)  # HC dès 3 kVA
    assert g.prix == {"hp": Decimal("0.1965"), "hc": Decimal("0.1467")}

    # Sélia élec vert Fixe, grille du 21/09/2026 (#68) : abonnements TRV, 27,36 c€ Base.
    g = grilles["selia_elec_vert_fixe_base"].en_vigueur(6, jour)
    assert g.abonnement_an == Decimal("190.32")  # 15,86 x 12
    assert g.prix["base"] == Decimal("0.2736")
    g = grilles["selia_elec_vert_fixe_hphc"].en_vigueur(6, jour)
    assert g.prix == {"hp": Decimal("0.2941"), "hc": Decimal("0.2139")}


def test_une_cle_par_offre_option(offres):
    cles = grilles_offres(offres)
    assert "la_bellenergie_prudence_base" in cles
    assert "la_bellenergie_prudence_hphc" in cles
    assert all(isinstance(g, Grilles) for g in cles.values())


def test_cout_option_prudence_sur_un_kwh(offres):
    """1 kWh un jour : abonnement au prorata (184,32 €/an ÷ 365) + 19,68 c€."""
    grilles = grilles_offres(offres)
    cout = cout_option(
        "la_bellenergie_prudence_base", grilles["la_bellenergie_prudence_base"], 6, UN_JOUR, PLAGES
    )
    assert cout.total == (Decimal("184.32") / Decimal("365") + Decimal("0.1968")).quantize(Decimal("0.01"))


def test_comparaison_trv_contre_offres(offres):
    """Le classement mélange TRV et offres.

    Avec 10 kWh dans la journée : Primeo Fixe Confort Base (16,74 c€, 241,92 €/an)
    bat le TRV Base (20,01 c€, 190,81 €/an) et GEG (18,37 c€ mais grille du 05/10).
    """
    from custom_components.tarifenergie.const import OPTIONS
    from custom_components.tarifenergie.modele import Grilles as GrillesTRV

    grilles = {option: GrillesTRV.charger(option) for option in OPTIONS}
    grilles.update(grilles_offres(offres))
    comp = comparer(grilles, 6, DIX_KWH, PLAGES, "base")
    assert comp.moins_chere.option == "primeo_fixe_confort_base"
    trv = comp.couts["base"]
    moins_chere = comp.couts[comp.moins_chere.option]
    assert comp.economie == (trv.total - moins_chere.total).quantize(Decimal("0.01"))
    # Puissance non proposée par l'offre : indisponible, avec la raison.
    comp3 = comparer(grilles, 3, DIX_KWH, PLAGES, "base")
    assert "la_bellenergie_prudence_hphc" in comp3.indisponibles


VALIDE = {
    "id": "x_base",
    "fournisseur": "F",
    "offre": "O",
    "option": "base",
    "issue": 999,
    "type_prix": "fixe",
    "grille_du": date(2026, 8, 1),
    "duree_fixite_mois": 12,
    "source": "https://exemple.fr",
    "abonnement_mensuel_ttc": {6: 15.0},
    "kwh_ttc": {"base": 0.2},
}


def _offre(**modifs):
    donnees = {**VALIDE, **modifs}
    return {k: v for k, v in donnees.items() if v is not None}


def test_offre_option_valide():
    offre = offre_depuis_dict(_offre(), "x_base")
    assert (offre.option, offre.issue, offre.territoire) == ("base", 999, "enedis")
    assert offre.libelle == "F O (Base)"
    assert offre.grilles.en_vigueur(6, date(2026, 10, 19)).abonnement_an == Decimal("180.0")


@pytest.mark.parametrize(
    ("donnees", "ident", "chemin_fautif"),
    [
        # Regroupement de plusieurs options dans un fichier : refusé (#343).
        (
            _offre(
                options={"base": {}, "hphc": {}},
                option=None,
                abonnement_mensuel_ttc=None,
                kwh_ttc=None,
            ),
            "x_base",
            "offre.options",
        ),
        (_offre(), "autre_base", "offre.id"),
        (_offre(id="x", option="base"), "x", "offre.id"),  # sans suffixe _<option>
        (_offre(option="tempo", id="x_tempo"), "x_tempo", "offre.option"),
        (_offre(issue=None), "x_base", "champs manquants"),
        (_offre(issue=0), "x_base", "offre.issue"),
        (_offre(couleur="bleu"), "x_base", "champs inconnus"),
        (_offre(type_prix="indexe"), "x_base", "offre.type_prix"),
        (_offre(duree_fixite_mois=True), "x_base", "offre.duree_fixite_mois"),
        (_offre(grille_du="2026-08-01"), "x_base", "offre.grille_du"),
        (_offre(source=" "), "x_base", "offre.source"),
        (_offre(territoire="es"), "x_base", "offre.territoire"),
        (_offre(abonnement_mensuel_ttc={42: 11.0}), "x_base", "abonnement_mensuel_ttc"),
        (_offre(abonnement_mensuel_ttc={}), "x_base", "abonnement_mensuel_ttc"),
        (_offre(abonnement_mensuel_ttc={6: -1}), "x_base", r"abonnement_mensuel_ttc\[6\]"),
        # Postes qui ne correspondent pas à l'option.
        (_offre(kwh_ttc={"hp": 0.2, "hc": 0.1}), "x_base", "offre.kwh_ttc"),
        (_offre(option="hphc", id="x_hphc", kwh_ttc={"hp": 0.2}), "x_hphc", "offre.kwh_ttc"),
        (_offre(kwh_ttc={}), "x_base", "offre.kwh_ttc"),
        (_offre(kwh_ttc=None), "x_base", "exclusifs"),
        (_offre(kwh_ttc_par_puissance={6: {"base": 0.2}}), "x_base", "exclusifs"),
        (_offre(kwh_ttc=None, kwh_ttc_par_puissance={}), "x_base", "kwh_ttc_par_puissance"),
        (
            _offre(kwh_ttc=None, kwh_ttc_par_puissance={9: {"base": 0.2}}),
            "x_base",
            r"kwh_ttc_par_puissance\[9\]",
        ),
        ([], "x_base", "offre"),
    ],
)
def test_offres_invalides(donnees, ident, chemin_fautif):
    with pytest.raises(OffreInvalide, match=chemin_fautif):
        offre_depuis_dict(donnees, ident)


def _ecrire(dossier, nom, contenu):
    (dossier / nom).write_text(contenu, encoding="utf-8")


def test_fichiers_invalides(tmp_path):
    _ecrire(tmp_path, "x_base.yaml", "id: [")
    with pytest.raises(OffreInvalide, match="YAML invalide"):
        charger_offre(tmp_path / "x_base.yaml")
    (tmp_path / "y_base.yaml").write_bytes(b"\xff\xfe")
    with pytest.raises(OffreInvalide, match="illisible"):
        charger_offre(tmp_path / "y_base.yaml")
    _ecrire(tmp_path, "z_base.yaml", "id: autre_base\n")
    with pytest.raises(OffreInvalide, match=r"z_base\.yaml"):
        charger_offre(tmp_path / "z_base.yaml")


def test_une_issue_par_offre_option(tmp_path):
    """Deux fichiers qui documentent la même issue : refusé (une issue = une offre-option)."""
    gabarit = yaml.safe_dump(VALIDE)
    _ecrire(tmp_path, "x_base.yaml", gabarit)
    _ecrire(tmp_path, "y_base.yaml", gabarit.replace("id: x_base", "id: y_base"))
    with pytest.raises(OffreInvalide, match="issue #999 déjà utilisée par x_base"):
        lire_offres(tmp_path)


def test_exclusion_hors_territoire():
    """Offre-option d'une ELD : exclue d'un site Enedis avec la raison, comparée pour un site ELD (#345)."""
    eld = offre_depuis_dict(_offre(territoire="eld:es_strasbourg"), "x_base")
    enedis = offre_depuis_dict(_offre(id="y_base", issue=998), "y_base")
    offres = {"x_base": eld, "y_base": enedis}
    assert exclusions(offres, "enedis") == {
        "x_base": "non disponible dans cette zone (offre eld:es_strasbourg, site enedis)"
    }
    assert sorted(exclusions(offres, "eld:es_strasbourg")) == ["y_base"]
    comp = comparer(grilles_offres(offres), 6, UN_JOUR, PLAGES, "base", exclusions(offres, "enedis"))
    assert sorted(comp.couts) == ["y_base"]
    assert "non disponible" in comp.indisponibles["x_base"]
