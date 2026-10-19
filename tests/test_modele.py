"""Grilles CRE : lecture des fichiers réels et recherche du tarif en vigueur."""

import itertools
from datetime import date, timedelta
from decimal import Decimal

import pytest

from custom_components.tarifenergie.modele import Grilles, TarifIntrouvable, lire_grilles


@pytest.fixture(scope="module")
def base() -> Grilles:
    return Grilles.charger("base")


@pytest.fixture(scope="module")
def hphc() -> Grilles:
    return Grilles.charger("hphc")


def test_valeurs_publiees_par_la_cre(base, hphc):
    """Valeurs relevées dans les fichiers CRE (grille du 01/08/2026, 6 kVA, TTC)."""
    g = base.en_vigueur(6, date(2026, 10, 18))
    assert (g.debut, g.fin, g.abonnement_an, g.prix) == (
        date(2026, 8, 1),
        None,
        Decimal("190.81"),
        {"base": Decimal("0.2001")},
    )
    g = hphc.en_vigueur(9, date(2026, 10, 18))
    assert g.prix == {"hp": Decimal("0.2142"), "hc": Decimal("0.1589")}
    assert g.abonnement_an == Decimal("239.8378787")


def test_grille_du_jour_et_changement_au_1er_aout(base):
    assert base.en_vigueur(6, date(2026, 7, 31)).debut == date(2026, 2, 1)
    assert base.en_vigueur(6, date(2026, 8, 1)).debut == date(2026, 8, 1)
    assert base.en_vigueur(6, date(2026, 7, 31)).prix["base"] == Decimal("0.1940")


@pytest.mark.parametrize("option", ["base", "hphc"])
def test_periodes_continues_sans_chevauchement(option):
    """Chaque grille commence le lendemain de la fin de la précédente : aucun jour sans tarif."""
    par_puissance: dict[int, list] = {}
    for g in lire_grilles(option):
        par_puissance.setdefault(g.puissance, []).append(g)
    for liste in par_puissance.values():
        liste.sort(key=lambda g: g.debut)
        for avant, apres in itertools.pairwise(liste):
            assert avant.fin is not None
            assert avant.fin + timedelta(days=1) == apres.debut
        assert liste[-1].fin is None


def test_puissances_publiees(base, hphc):
    # La CRE ne publie l'option Base que jusqu'à 15 kVA ; Heures creuses à 3 kVA depuis le 01/08/2026.
    assert base.puissances() == [3, 6, 9, 12, 15]
    assert hphc.puissances() == [3, 6, 9, 12, 15, 18, 24, 30, 36]
    with pytest.raises(TarifIntrouvable):
        base.en_vigueur(36, date(2026, 10, 1))
    with pytest.raises(TarifIntrouvable):
        hphc.en_vigueur(3, date(2026, 7, 31))
    with pytest.raises(TarifIntrouvable):
        base.en_vigueur(6, date(2012, 7, 22))
    assert base.derniere(6).debut == date(2026, 8, 1)
    assert base.derniere(36) is None


def test_fichier_mal_forme(tmp_path):
    entete = "DATE_DEBUT;DATE_FIN;P_SOUSCRITE;PART_FIXE_HT;PART_FIXE_TTC;PART_VARIABLE_HT;PART_VARIABLE_TTC\n"
    fichier = tmp_path / "x.csv"
    fichier.write_text(entete + "01/08/2026;;6;1;2;3;abc\n", encoding="utf-8")
    with pytest.raises(ValueError, match="nombre invalide"):
        lire_grilles("base", fichier)
    fichier.write_text(entete + ";;6;1;2;3;4\n", encoding="utf-8")
    with pytest.raises(ValueError, match="DATE_DEBUT"):
        lire_grilles("base", fichier)
    fichier.write_text(entete + "01/08/2026;;6;;;;\n", encoding="utf-8")
    assert lire_grilles("base", fichier) == []
