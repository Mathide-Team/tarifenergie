"""Capteurs créés à partir d'une consommation horaire, et lecture réelle des statistiques.

Identifiants d'entité en anglais : langue par défaut de Home Assistant en test.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
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
    # Tempo (#340) : 1er-3 octobre 2026, jours bleus réels (veille comprise pour 0h-6h),
    # 0h-6h en HC Tempo : 36 kWh à 0,1356 + 3 jours de 189,9802924 €/an = 6,44 €.
    tempo = hass.states.get("sensor.maison_12_month_cost_tempo_option")
    assert tempo.state == "6.44"
    assert tempo.attributes["kwh"] == {"hc_bleu": 36.0}
    assert "jours_couleur_estimee" not in tempo.attributes
    # Offres de marché (issues #40, #44, #63, #64 et lot 2) : à cette consommation
    # nocturne, Tempo puis Primeo Fixe Confort HC (13,44 c€) sont les moins chers ; les
    # grilles postérieures au 3 octobre (GEG 05/10, Ohm 14/10 et 16/10) sont indisponibles.
    prudence = hass.states.get("sensor.maison_12_month_cost_la_bellenergie_prudence_off_peak")
    assert prudence is not None
    assert prudence.state == "7.15"
    assert prudence.attributes["kwh"] == {"hp": 0.0, "hc": 36.0}
    assert hass.states.get("sensor.maison_cheapest_option").state == "tempo"
    economie = hass.states.get("sensor.maison_possible_12_month_saving")
    assert economie.state == "2.33"
    assert [e["option"] for e in economie.attributes["classement"]] == [
        "tempo",
        "primeo_fixe_confort_hphc",
        "plenitude_pleniweb_1an_hphc",
        "la_bellenergie_prudence_hphc",
        "alterna_fixe_1an_hphc",
        "hphc",
        "alterna_du_coin_1an_hphc",
        "la_bellenergie_constance_hphc",
        "la_bellenergie_garance_hphc",
        "primeo_fixe_confort_base",
        "plenitude_pleniweb_1an_base",
        "la_bellenergie_prudence_base",
        "alterna_fixe_1an_base",
        "base",
        "alterna_du_coin_1an_base",
        "la_bellenergie_constance_base",
        "la_bellenergie_garance_base",
        "selia_elec_vert_fixe_hphc",
        "ilek_enrfixe_plus_hphc",
        "ilek_enrfixe_plus_base",
        "selia_elec_vert_fixe_base",
    ]
    assert "2026-10-01" in economie.attributes["indisponibles"]["geg_elec_verte_3ans_base"]
    assert "2026-10-01" in economie.attributes["indisponibles"]["ohm_serente_fixe_1an_base"]
    assert hass.states.get("sensor.maison_12_month_consumption").state == "36.0"
    assert hass.states.get("sensor.maison_off_peak_share").state == "100.0"
    assert await hass.config_entries.async_unload(entree.entry_id)


async def test_option_indisponible_au_dela_de_15_kva(hass: HomeAssistant):
    await _installer(hass, _nuit(), {**DONNEES, "puissance": 36, "option_actuelle": "hphc"})
    base = hass.states.get("sensor.maison_12_month_cost_base_option")
    assert base.state == "unknown"
    assert "36 kVA" in base.attributes["indisponible"]
    # À 36 kVA, Tempo (649,02 €/an, HC bleu 13,56 c€ : 10,22 €) passe devant Plenitude HC
    # (681,72 €/an, 14,67 c€), Prudence HC et le TRV HC.
    assert hass.states.get("sensor.maison_cheapest_option").state == "tempo"
    assert hass.states.get("sensor.maison_12_month_cost_tempo_option").state == "10.22"
    assert hass.states.get("sensor.maison_possible_12_month_saving").state == "0.85"


async def test_tempo_jours_estimes(hass: HomeAssistant):
    """Jours absents de l'historique réel : couleur estimée selon les règles, et signalée."""
    debut = datetime(2027, 1, 11, tzinfo=dt_util.get_default_time_zone())  # lundi, hors historique
    conso = [(debut + timedelta(days=j, hours=h), 1.0) for j in range(5) for h in range(24)]
    await _installer(hass, conso)
    tempo = hass.states.get("sensor.maison_12_month_cost_tempo_option")
    assert tempo.attributes["jours_couleur_estimee"] == 6  # du dimanche 10 (0h-6h du lundi) au vendredi 15
    assert sum(tempo.attributes["kwh"].values()) == 120.0


async def test_sans_donnees(hass: HomeAssistant):
    await _installer(hass, [])
    # Sans consommation, toutes les options coûtent 0,00 € : le classement départage
    # les ex æquo par ordre alphabétique de la clé de comparaison.
    assert hass.states.get("sensor.maison_cheapest_option").state == "alterna_du_coin_1an_base"
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


async def test_plages_detectees_par_la_teleinformation(hass: HomeAssistant):
    """#370 : index HC et HP configurés, plages détectées (23h-7h) au lieu de la saisie (22h-6h)."""
    debut = datetime(2026, 10, 1, tzinfo=dt_util.get_default_time_zone())
    heures = [debut + timedelta(hours=i) for i in range(5 * 24)]
    creuse = [h.hour >= 23 or h.hour < 7 for h in heures]
    series = {
        CAPTEUR: [(h, 1.0) for h in heures],
        "sensor.index_hc": [(h, 1.0 if c else 0.0) for h, c in zip(heures, creuse, strict=True)],
        "sensor.index_hp": [(h, 0.0 if c else 1.0) for h, c in zip(heures, creuse, strict=True)],
    }
    donnees = {**DONNEES, "index_hc": "sensor.index_hc", "index_hp": "sensor.index_hp"}
    entree = MockConfigEntry(domain=DOMAIN, title="Maison", unique_id=CAPTEUR, data=donnees)
    entree.add_to_hass(hass)

    async def lire(_hass, entite, _debut, _fin):
        return series[entite]

    with patch("custom_components.tarifenergie.coordinateur.async_conso_horaire", side_effect=lire):
        assert await hass.config_entries.async_setup(entree.entry_id)
        await hass.async_block_till_done()
    part = hass.states.get("sensor.maison_off_peak_share")
    assert part.attributes["plages_hc"] == [{"depuis": None, "plages": "23:00-07:00"}]
    assert part.attributes["source_plages_hc"] == "teleinformation"
    assert float(part.state) == pytest.approx(8 / 24 * 100, abs=0.01)
    hphc = hass.states.get("sensor.maison_12_month_cost_off_peak_option")
    assert hphc.attributes["source_plages_hc"] == "teleinformation"


async def test_teleinformation_sans_plages_exploitables(hass: HomeAssistant):
    """Index muets : la saisie sert, et l'origine l'indique."""
    donnees = {**DONNEES, "index_hc": "sensor.index_hc", "index_hp": "sensor.index_hp"}
    entree = MockConfigEntry(domain=DOMAIN, title="Maison", unique_id=CAPTEUR, data=donnees)
    entree.add_to_hass(hass)

    async def lire(_hass, entite, _debut, _fin):
        return _nuit() if entite == CAPTEUR else []

    with patch("custom_components.tarifenergie.coordinateur.async_conso_horaire", side_effect=lire):
        assert await hass.config_entries.async_setup(entree.entry_id)
        await hass.async_block_till_done()
    part = hass.states.get("sensor.maison_off_peak_share")
    assert part.attributes == {**part.attributes, "source_plages_hc": "saisie"}
    assert part.attributes["plages_hc"] == [{"depuis": None, "plages": "22:00-06:00"}]
