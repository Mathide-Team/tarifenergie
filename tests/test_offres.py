"""Offres de marché (issues #5 et #6) : lecture des YAML livrés, validation, comparaison."""

from datetime import datetime
from decimal import Decimal

import pytest

from custom_components.tarifenergie.calcul import PlagesHC, comparer, cout_option
from custom_components.tarifenergie.modele import Grilles, TarifIntrouvable
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
        "alterna_du_coin_1an",
        "alterna_fixe_1an",
        "es_trv_local",
        "es_verte_fixe_1an",
        "es_verte_regionale_fixe_1an",
        "gedia_all_inclusive",
        "geg_elec_verte_3ans",
        "hunelec_prix_fixe_1an",
        "hunelec_prix_fixe_1an_vert",
        "ilek_enrfixe_plus",
        "la_bellenergie_constance",
        "la_bellenergie_garance",
        "la_bellenergie_prudence",
        "ohm_fixe_2ans",
        "ohm_serente_fixe_1an",
        "oya_trv_local",
        "plenitude_pleniweb_1an",
        "primeo_fixe_confort",
        "selia_elec_vert_fixe",
    ]
    assert all(o.grilles["base"] for o in offres.values())


def test_hunelec_grilles_du_1er_juillet_2026(offres):
    """Grilles TTC Hunélec du 01/07/2026, page 4 des fiches (#325-#328)."""
    grilles = grilles_offres(offres)
    jour = datetime(2026, 10, 19).date()
    g = grilles["hunelec_prix_fixe_1an:base"].en_vigueur(3, jour)
    assert (g.debut, g.abonnement_an, g.prix) == (
        datetime(2026, 7, 1).date(),
        Decimal("144.84"),  # 12,07 x 12
        {"base": Decimal("0.23506")},
    )
    # kWh Base : 0,23506 € jusqu'à 6 kVA, 0,23346 € au-delà.
    assert grilles["hunelec_prix_fixe_1an:base"].en_vigueur(9, jour).prix == {"base": Decimal("0.23346")}
    g = grilles["hunelec_prix_fixe_1an:hphc"].en_vigueur(36, jour)
    assert g.abonnement_an == Decimal("652.44")  # 54,37 x 12
    assert g.prix == {"hp": Decimal("0.25019"), "hc": Decimal("0.19129")}
    with pytest.raises(TarifIntrouvable, match="3 kVA"):  # pas d'option HC en 3 kVA
        grilles["hunelec_prix_fixe_1an:hphc"].en_vigueur(3, jour)
    # 100 % vert : même grille + 2,27 € TTC/mois de supplément, ajouté à l'abonnement.
    g = grilles["hunelec_prix_fixe_1an_vert:base"].en_vigueur(3, jour)
    assert g.abonnement_an == Decimal("172.08")  # (12,07 + 2,27) x 12
    assert g.prix == {"base": Decimal("0.23506")}
    g = grilles["hunelec_prix_fixe_1an_vert:hphc"].en_vigueur(6, jour)
    assert g.abonnement_an == Decimal("218.76")  # (15,96 + 2,27) x 12
    assert g.prix == {"hp": Decimal("0.25019"), "hc": Decimal("0.19129")}


def test_es_grilles_du_1er_octobre_2026(offres):
    """Grilles TTC ÉS Énergies du 01/10/2026, page 1 des fiches (#73, #74, #329, #332)."""
    grilles = grilles_offres(offres)
    jour = datetime(2026, 10, 19).date()
    g = grilles["es_verte_fixe_1an:base"].en_vigueur(6, jour)
    assert (g.debut, g.abonnement_an, g.prix) == (
        datetime(2026, 10, 1).date(),
        Decimal("191.40"),  # 15,95 x 12
        {"base": Decimal("0.30216")},
    )
    # Cellules fusionnées : 0,30216 € pour 3-6 kVA, 0,29981 € de 9 à 36 kVA.
    assert grilles["es_verte_fixe_1an:base"].en_vigueur(9, jour).prix == {"base": Decimal("0.29981")}
    g = grilles["es_verte_fixe_1an:hphc"].en_vigueur(36, jour)
    assert g.abonnement_an == Decimal("669.12")  # 55,76 x 12
    assert g.prix == {"hp": Decimal("0.32356"), "hc": Decimal("0.24000")}
    with pytest.raises(TarifIntrouvable, match="3 kVA"):  # pas d'option HC en 3 kVA
        grilles["es_verte_fixe_1an:hphc"].en_vigueur(3, jour)
    # 100 % régionale : + 2,27 € TTC/mois, ajouté à l'abonnement.
    assert grilles["es_verte_regionale_fixe_1an:base"].en_vigueur(3, jour).abonnement_an == Decimal("173.40")
    assert grilles["es_verte_regionale_fixe_1an:hphc"].en_vigueur(6, jour).abonnement_an == Decimal("221.40")


def test_gedia_grille_du_19_octobre_2026(offres):
    """GEDIA All Inclusive, tableau « Domestique » du 19-25/10/2026 (#54, #335) : abonnement en €/an."""
    grilles = grilles_offres(offres)
    jour = datetime(2026, 10, 19).date()
    g = grilles["gedia_all_inclusive:base"].en_vigueur(6, jour)
    assert (g.debut, g.abonnement_an, g.prix) == (
        datetime(2026, 10, 19).date(),
        Decimal("190.36"),  # publié en €/an, repris tel quel
        {"base": Decimal("0.26948")},
    )
    assert grilles["gedia_all_inclusive:base"].en_vigueur(9, jour).prix == {"base": Decimal("0.26725")}
    g = grilles["gedia_all_inclusive:hphc"].en_vigueur(15, jour)
    assert g.abonnement_an == Decimal("328.78")
    assert g.prix == {"hp": Decimal("0.28965"), "hc": Decimal("0.21082")}
    with pytest.raises(TarifIntrouvable, match="3 kVA"):
        grilles["gedia_all_inclusive:hphc"].en_vigueur(3, jour)


def test_es_trv_local_grille_du_1er_aout_2026(offres):
    """TRV local ÉS (#72, #190) : type « reglemente », sans durée de fixité, HC dès 3 kVA."""
    offre = offres["es_trv_local"]
    assert (offre.type_prix, offre.eld, offre.duree_fixite_mois) == (
        "reglemente",
        "strasbourg_electricite_reseaux",
        None,
    )
    grilles = grilles_offres(offres)
    jour = datetime(2026, 10, 19).date()
    g = grilles["es_trv_local:base"].en_vigueur(6, jour)
    assert (g.debut, g.abonnement_an, g.prix) == (
        datetime(2026, 8, 1).date(),
        Decimal("191.40"),  # 15,95 x 12
        {"base": Decimal("0.20006")},
    )
    assert grilles["es_trv_local:base"].en_vigueur(9, jour).prix == {"base": Decimal("0.19850")}
    g = grilles["es_trv_local:hphc"].en_vigueur(3, jour)  # HC proposée dès 3 kVA
    assert g.abonnement_an == Decimal("147.48")  # 12,29 x 12
    assert g.prix == {"hp": Decimal("0.21422"), "hc": Decimal("0.15890")}


def test_oya_trv_local_grille_du_1er_aout_2026(offres):
    """TRV local Oya énergies (#215, #216)."""
    offre = offres["oya_trv_local"]
    assert (offre.type_prix, offre.eld, offre.duree_fixite_mois) == ("reglemente", "oya_energies", None)
    grilles = grilles_offres(offres)
    jour = datetime(2026, 10, 24).date()
    g = grilles["oya_trv_local:base"].en_vigueur(6, jour)
    assert (g.debut, g.abonnement_an, g.prix) == (
        datetime(2026, 8, 1).date(),
        Decimal("190.32"),
        {"base": Decimal("0.2001")},
    )
    # Base 9-36 kVA en extinction, publiée pour les contrats en cours
    g = grilles["oya_trv_local:base"].en_vigueur(36, jour)
    assert (g.abonnement_an, g.prix) == (Decimal("646.56"), {"base": Decimal("0.1985")})
    g = grilles["oya_trv_local:hphc"].en_vigueur(36, jour)
    assert g.abonnement_an == Decimal("646.56")
    assert g.prix == {"hp": Decimal("0.2142"), "hc": Decimal("0.1589")}


@pytest.mark.parametrize(
    ("extra", "chemin_fautif"),
    [
        ({"duree_fixite_mois": 12, "eld": "x"}, "offre.duree_fixite_mois"),  # sans objet pour un TRV
        ({}, "offre.eld"),  # réseau de l'ELD exigé
    ],
)
def test_trv_local_invalide(extra, chemin_fautif):
    from datetime import date

    donnees = {
        "id": "x",
        "fournisseur": "F",
        "offre": "TRV local",
        "type_prix": "reglemente",
        "grille_du": date(2026, 8, 1),
        "source": "https://exemple.fr/trv.pdf",
        "options": {"base": {"abonnement_mensuel_ttc": {6: 15.0}, "kwh_ttc": {"base": 0.2}}},
        **extra,
    }
    with pytest.raises(OffreInvalide, match=chemin_fautif):
        offre_depuis_dict(donnees, "x")


def test_abonnement_annuel_et_mensuel_exclusifs():
    """abonnement_annuel_ttc repris tel quel ; les deux champs ensemble sont refusés."""
    from datetime import date

    base = {
        "id": "x",
        "fournisseur": "F",
        "offre": "O",
        "type_prix": "fixe",
        "grille_du": date(2026, 10, 1),
        "duree_fixite_mois": 12,
        "source": "https://exemple.fr/grille.pdf",
    }
    annuel = {"abonnement_annuel_ttc": {6: 190.36}, "kwh_ttc": {"base": 0.2}}
    offre = offre_depuis_dict({**base, "options": {"base": annuel}}, "x")
    assert offre.grilles["base"].en_vigueur(6, date(2026, 10, 2)).abonnement_an == Decimal("190.36")
    deux = {**annuel, "abonnement_mensuel_ttc": {6: 15.0}}
    with pytest.raises(OffreInvalide, match="exclusifs"):
        offre_depuis_dict({**base, "options": {"base": deux}}, "x")


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


def test_lot_2_offres_fixes(offres):
    """Lot 2 (issues #38, #43, #56, #57, #61, #62, #65, #68) : valeurs citées des grilles."""
    grilles = grilles_offres(offres)
    jour = datetime(2026, 10, 19).date()

    # Ohm Fixe 2 ans, grille du 16/10/2026 (#38) : 6 kVA 15,88 €/mois, 22,49 c€.
    g = grilles["ohm_fixe_2ans:base"].en_vigueur(6, jour)
    assert (g.debut, g.abonnement_an, g.prix["base"]) == (
        datetime(2026, 10, 16).date(),
        Decimal("190.56"),  # 15,88 x 12
        Decimal("0.2249"),
    )
    g = grilles["ohm_fixe_2ans:hphc"].en_vigueur(6, jour)
    assert g.prix == {"hp": Decimal("0.2421"), "hc": Decimal("0.1771")}

    # Alterna du coin 1 an, grille du 01/09/2026 (#43) : 6 kVA 17,66 €/mois, 19,68 c€.
    g = grilles["alterna_du_coin_1an:base"].en_vigueur(6, jour)
    assert g.abonnement_an == Decimal("211.92")  # 17,66 x 12
    assert g.prix["base"] == Decimal("0.1968")
    g = grilles["alterna_du_coin_1an:hphc"].en_vigueur(3, jour)  # HC dès 3 kVA
    assert g.abonnement_an == Decimal("167.16")  # 13,93 x 12
    assert g.prix == {"hp": Decimal("0.2107"), "hc": Decimal("0.1565")}

    # GEG fixe 3 ans, grille du 05/10/2026 (#56) : kWh HC/HP selon la puissance.
    g = grilles["geg_elec_verte_3ans:hphc"].en_vigueur(6, jour)
    assert g.prix == {"hp": Decimal("0.1983"), "hc": Decimal("0.1584")}
    g = grilles["geg_elec_verte_3ans:hphc"].en_vigueur(12, jour)
    assert g.prix == {"hp": Decimal("0.2014"), "hc": Decimal("0.1584")}
    g = grilles["geg_elec_verte_3ans:hphc"].en_vigueur(18, jour)
    assert g.prix == {"hp": Decimal("0.2014"), "hc": Decimal("0.1656")}
    g = grilles["geg_elec_verte_3ans:base"].en_vigueur(3, jour)
    assert g.prix["base"] == Decimal("0.1837")

    # ilek ÉnRFixe+, grille d'octobre 2026 (#57) : 6 kVA 25,10 €/mois, 24,00 c€.
    g = grilles["ilek_enrfixe_plus:base"].en_vigueur(6, jour)
    assert g.abonnement_an == Decimal("301.20")  # 25,10 x 12
    assert g.prix["base"] == Decimal("0.2400")

    # Primeo Fixe Confort, grille du 01/08/2026 (#61) : 6 kVA 20,16 €/mois, 16,74 c€.
    g = grilles["primeo_fixe_confort:base"].en_vigueur(6, jour)
    assert g.abonnement_an == Decimal("241.92")  # 20,16 x 12
    assert g.prix["base"] == Decimal("0.1674")
    g = grilles["primeo_fixe_confort:hphc"].en_vigueur(6, jour)
    assert g.prix == {"hp": Decimal("0.1787"), "hc": Decimal("0.1344")}

    # la bellenergie Constance, grille du 01/08/2026 (#62) : 6 kVA 17,87 €/mois.
    g = grilles["la_bellenergie_constance:base"].en_vigueur(6, jour)
    assert g.abonnement_an == Decimal("214.44")  # 17,87 x 12
    assert g.prix["base"] == Decimal("0.1968")
    g = grilles["la_bellenergie_constance:hphc"].en_vigueur(9, jour)
    assert g.abonnement_an == Decimal("266.04")  # 22,17 x 12

    # Plenitude Pleniweb 1 an, grille du 01/10/2026 (#65) : 6 kVA 18,26 €/mois, 18,37 c€.
    g = grilles["plenitude_pleniweb_1an:base"].en_vigueur(6, jour)
    assert g.abonnement_an == Decimal("219.12")  # 18,26 x 12
    assert g.prix["base"] == Decimal("0.1837")
    g = grilles["plenitude_pleniweb_1an:hphc"].en_vigueur(3, jour)  # HC dès 3 kVA
    assert g.prix == {"hp": Decimal("0.1965"), "hc": Decimal("0.1467")}

    # Sélia élec vert Fixe, grille du 21/09/2026 (#68) : abonnements TRV, 27,36 c€ Base.
    g = grilles["selia_elec_vert_fixe:base"].en_vigueur(6, jour)
    assert g.abonnement_an == Decimal("190.32")  # 15,86 x 12
    assert g.prix["base"] == Decimal("0.2736")
    g = grilles["selia_elec_vert_fixe:hphc"].en_vigueur(6, jour)
    assert g.prix == {"hp": Decimal("0.2941"), "hc": Decimal("0.2139")}


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

    Avec 10 kWh dans la journée : Primeo Fixe Confort Base (16,74 c€, 241,92 €/an)
    bat le TRV Base (20,01 c€, 190,81 €/an) et GEG (18,37 c€ mais grille du 05/10).
    """
    from custom_components.tarifenergie.const import OPTIONS
    from custom_components.tarifenergie.modele import Grilles as GrillesTRV

    grilles = {option: GrillesTRV.charger(option) for option in OPTIONS}
    grilles.update(grilles_offres(offres))
    comp = comparer(grilles, 6, DIX_KWH, PLAGES, "base")
    assert comp.moins_chere.option == "primeo_fixe_confort:base"
    trv = comp.couts["base"]
    moins_chere = comp.couts[comp.moins_chere.option]
    assert comp.economie == (trv.total - moins_chere.total).quantize(Decimal("0.01"))
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


def test_cles_par_option(offres):
    """``Offre.cles()`` : une clé ``<id>:<option>`` par option proposée, triée."""
    for offre in offres.values():
        assert offre.cles() == [f"{offre.id}:{option}" for option in sorted(offre.grilles)]


def test_charger_offre_yaml_invalide(tmp_path):
    """YAML illisible : OffreInvalide qui nomme le fichier (issue #418 : cause journalisée)."""
    from custom_components.tarifenergie.offres import charger_offre

    chemin = tmp_path / "casse.yaml"
    chemin.write_text("id: [non fermé\n", encoding="utf-8")
    with pytest.raises(OffreInvalide, match=r"casse\.yaml : YAML invalide"):
        charger_offre(chemin)


def test_charger_offre_fichier_illisible(tmp_path):
    """Octets non UTF-8 : OffreInvalide « fichier illisible »."""
    from custom_components.tarifenergie.offres import charger_offre

    chemin = tmp_path / "binaire.yaml"
    chemin.write_bytes(b"\xff\xfe\x00offre")
    with pytest.raises(OffreInvalide, match=r"binaire\.yaml : fichier illisible"):
        charger_offre(chemin)


def test_charger_offre_contenu_invalide(tmp_path):
    """YAML valide mais offre incomplète : le nom du fichier préfixe l'erreur de validation."""
    from custom_components.tarifenergie.offres import charger_offre

    chemin = tmp_path / "incomplete.yaml"
    chemin.write_text("id: x\n", encoding="utf-8")
    with pytest.raises(OffreInvalide, match=r"^incomplete\.yaml : "):
        charger_offre(chemin)
