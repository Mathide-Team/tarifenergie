"""Capteurs créés à partir d'une consommation horaire, et lecture réelle des statistiques.

Identifiants d'entité en anglais : langue par défaut de Home Assistant en test.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import async_wait_recording_done

from custom_components.tarifenergie.const import DOMAIN
from custom_components.tarifenergie.coordinateur import async_conso_horaire

CAPTEUR = "sensor.linky"
DONNEES = {
    "entite_energie": CAPTEUR,
    "puissance": 6,
    "option_actuelle": "base",
    "heures_creuses": "22:00-06:00",
}


def _nuit(jours: int = 3) -> list[tuple[datetime, float]]:
    """2 kWh par heure de 0 h à 6 h : tout en heures creuses."""
    debut = datetime(2026, 10, 1, tzinfo=dt_util.get_default_time_zone())
    return [(debut + timedelta(days=j, hours=h), 2.0) for j in range(jours) for h in range(6)]


async def _installer(hass: HomeAssistant, conso, donnees=DONNEES) -> MockConfigEntry:
    entree = MockConfigEntry(domain=DOMAIN, title="Maison", unique_id=CAPTEUR, data=donnees)
    entree.add_to_hass(hass)
    with patch("custom_components.tarifenergie.coordinateur.async_conso_horaire", return_value=conso):
        assert await hass.config_entries.async_setup(entree.entry_id)
        await hass.async_block_till_done()
    return entree


async def test_capteurs(hass: HomeAssistant):
    entree = await _installer(hass, _nuit())
    assert entree.state is ConfigEntryState.LOADED
    base = hass.states.get("sensor.maison_12_month_cost_base_option")
    hphc = hass.states.get("sensor.maison_12_month_cost_off_peak_option")
    # 36 kWh à 0,2001 + 3 jours de 190,81 €/an ; 36 kWh à 0,1589 + 3 jours de 190,8131821 €/an.
    assert base.state == "8.77"
    assert hphc.state == "7.29"
    assert base.attributes["unit_of_measurement"] == "EUR"
    assert base.attributes["kwh"] == {"base": 36.0}
    assert base.attributes["jours_couverts"] == 3
    assert base.attributes["grilles"] == ["2026-08-01"]
    # Offres de marché (issues #40, #44, #63, #64 et lot 2) : à cette consommation
    # nocturne, Primeo Fixe Confort HC (13,44 c€) est la moins chère ; les grilles
    # postérieures au 3 octobre (GEG 05/10, Ohm 14/10 et 16/10, GEDIA 19/10) sont indisponibles.
    prudence = hass.states.get("sensor.maison_12_month_cost_la_bellenergie_prudence_off_peak")
    assert prudence is not None
    assert prudence.state == "7.15"
    assert prudence.attributes["kwh"] == {"hp": 0.0, "hc": 36.0}
    assert hass.states.get("sensor.maison_cheapest_option").state == "primeo_fixe_confort:hphc"
    economie = hass.states.get("sensor.maison_possible_12_month_saving")
    assert economie.state == "1.94"
    assert [e["option"] for e in economie.attributes["classement"]] == [
        "primeo_fixe_confort:hphc",
        "plenitude_pleniweb_1an:hphc",
        "la_bellenergie_prudence:hphc",
        "alterna_fixe_1an:hphc",
        "hphc",
        # TRV local SÉOLIS HC (#234) : 7,30 €.
        "seolis_trv_local:hphc",
        # TRV local ÉS HC (#190) : 36 x 0,15890 + 3/365 x 194,16 = 7,316 €, juste
        # après le TRV national HC (abonnement un peu plus cher).
        "es_trv_local:hphc",
        "alterna_du_coin_1an:hphc",
        "la_bellenergie_constance:hphc",
        "la_bellenergie_garance:hphc",
        "primeo_fixe_confort:base",
        "plenitude_pleniweb_1an:base",
        # Hunélec HC (#326) : 36 x 0,19129 + 3/365 x 191,52 = 8,46 € ;
        # 100 % vert (#328) : + 2,27 €/mois = 8,68 € ; TRV Base : 8,77 €.
        "hunelec_prix_fixe_1an:hphc",
        "la_bellenergie_prudence:base",
        "alterna_fixe_1an:base",
        "hunelec_prix_fixe_1an_vert:hphc",
        "base",
        # TRV local SÉOLIS Base (#233) : 8,77 €, à égalité au centime avec
        # TRV national Base ; départage par le nom de l'option.
        "seolis_trv_local:base",
        # TRV local ÉS Base (#72) : 36 x 0,20006 + 3/365 x 191,40 = 8,775 € (TRV national : 8,772 €).
        "es_trv_local:base",
        "alterna_du_coin_1an:base",
        "la_bellenergie_constance:base",
        "la_bellenergie_garance:base",
        "selia_elec_vert_fixe:hphc",
        "ilek_enrfixe_plus:hphc",
        # Hunélec Base (#325, #327) : 36 x 0,23506 + 3/365 x 188,88 = 10,01 € (vert : 10,24 €).
        "hunelec_prix_fixe_1an:base",
        # ÉS HC (#329) : 36 x 0,24 + 3/365 x 194,16 = 10,2358 €, juste devant
        # Hunélec vert Base (10,2385 €) ; ÉS 100 % régionale HC (#332) : 10,46 €.
        "es_verte_fixe_1an:hphc",
        "hunelec_prix_fixe_1an_vert:base",
        "es_verte_regionale_fixe_1an:hphc",
        "ilek_enrfixe_plus:base",
        "selia_elec_vert_fixe:base",
        # ÉS Base (#73) : 36 x 0,30216 + 3/365 x 191,40 = 12,45 € ; régionale (#74) : 12,67 €.
        "es_verte_fixe_1an:base",
        "es_verte_regionale_fixe_1an:base",
    ]
    assert "2026-10-01" in economie.attributes["indisponibles"]["geg_elec_verte_3ans:base"]
    assert "2026-10-01" in economie.attributes["indisponibles"]["ohm_serente_fixe_1an:base"]
    assert "2026-10-01" in economie.attributes["indisponibles"]["gedia_all_inclusive:hphc"]
    assert hass.states.get("sensor.maison_12_month_consumption").state == "36.0"
    assert hass.states.get("sensor.maison_off_peak_share").state == "100.0"
    assert await hass.config_entries.async_unload(entree.entry_id)


async def test_option_indisponible_au_dela_de_15_kva(hass: HomeAssistant):
    await _installer(hass, _nuit(), {**DONNEES, "puissance": 36, "option_actuelle": "hphc"})
    base = hass.states.get("sensor.maison_12_month_cost_base_option")
    assert base.state == "unknown"
    assert "36 kVA" in base.attributes["indisponible"]
    # À 36 kVA, Plenitude HC (681,72 €/an, 14,67 c€) passe devant Prudence HC et le TRV HC.
    assert hass.states.get("sensor.maison_cheapest_option").state == "plenitude_pleniweb_1an:hphc"
    assert hass.states.get("sensor.maison_possible_12_month_saving").state == "0.19"


async def test_sans_donnees(hass: HomeAssistant):
    await _installer(hass, [])
    # Sans consommation, toutes les options coûtent 0,00 € : le classement départage
    # les ex æquo par ordre alphabétique de la clé de comparaison.
    assert hass.states.get("sensor.maison_cheapest_option").state == "alterna_du_coin_1an:base"
    assert hass.states.get("sensor.maison_off_peak_share").state == "unknown"
    await _installer_vide_hphc(hass)


async def _installer_vide_hphc(hass: HomeAssistant):
    """Sans aucune option calculable : capteurs inconnus, pas d'erreur."""
    coord = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    coord.grilles = {}
    with patch("custom_components.tarifenergie.coordinateur.async_conso_horaire", return_value=[]):
        await coord.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.maison_cheapest_option").state == "unknown"
    assert hass.states.get("sensor.maison_12_month_consumption").state == "unknown"
    assert hass.states.get("sensor.maison_possible_12_month_saving").state == "unknown"


async def test_lecture_des_statistiques_en_kwh(hass: HomeAssistant):
    """Statistiques réelles en Wh : converties en kWh, variations négatives écartées, heure locale."""
    debut = dt_util.utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(hours=3)
    metadata = {
        "source": "recorder",
        "statistic_id": CAPTEUR,
        "unit_of_measurement": "Wh",
        "unit_class": "energy",
        "has_sum": True,
        "mean_type": StatisticMeanType.NONE,
        "name": None,
    }
    sommes = [0, 1500, 1000, 3000]  # 0, +1,5 kWh, -0,5 (écartée), +2 kWh
    async_import_statistics(
        hass,
        metadata,
        [{"start": debut + timedelta(hours=i), "sum": s, "state": s} for i, s in enumerate(sommes)],
    )
    await async_wait_recording_done(hass)
    conso = await async_conso_horaire(hass, CAPTEUR, debut - timedelta(hours=1), debut + timedelta(hours=4))
    assert [round(k, 3) for _, k in conso] == [0.0, 1.5, 2.0]
    assert all(h.tzinfo == dt_util.get_default_time_zone() for h, _ in conso)
