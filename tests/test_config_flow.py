"""Flux de configuration et options."""

from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tarifenergie.const import DOMAIN

CAPTEUR = "sensor.linky"
SAISIE = {
    "nom": "Maison",
    "entite_energie": CAPTEUR,
    "puissance": "9",
    "option_actuelle": "base",
    "heures_creuses": "23h30-07h30",
}


@pytest.fixture(autouse=True)
def _capteur(hass: HomeAssistant):
    hass.states.async_set(CAPTEUR, "12345", {"unit_of_measurement": "kWh", "state_class": "total_increasing"})


@pytest.fixture(autouse=True)
def _sans_setup():
    with patch("custom_components.tarifenergie.async_setup_entry", return_value=True):
        yield


async def test_creation(hass: HomeAssistant):
    res = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert res["type"] is FlowResultType.FORM
    res = await hass.config_entries.flow.async_configure(res["flow_id"], SAISIE)
    assert res["type"] is FlowResultType.CREATE_ENTRY
    assert res["title"] == "Maison"
    assert res["data"] == {
        "entite_energie": CAPTEUR,
        "puissance": 9,
        "option_actuelle": "base",
        "heures_creuses": "23:30-07:30",
    }
    assert res["result"].unique_id == CAPTEUR


@pytest.mark.parametrize(
    ("attributs", "erreur"),
    [
        (None, "capteur_absent"),
        ({"unit_of_measurement": "m³", "state_class": "total_increasing"}, "unite"),
        ({"unit_of_measurement": "kWh", "state_class": "measurement"}, "state_class"),
    ],
)
async def test_capteur_refuse(hass: HomeAssistant, attributs, erreur):
    if attributs is None:
        hass.states.async_remove(CAPTEUR)
    else:
        hass.states.async_set(CAPTEUR, "1", attributs)
    res = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    res = await hass.config_entries.flow.async_configure(res["flow_id"], SAISIE)
    assert res["errors"] == {"entite_energie": erreur}


async def test_plages_refusees_puis_corrigees(hass: HomeAssistant):
    res = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    res = await hass.config_entries.flow.async_configure(
        res["flow_id"], {**SAISIE, "heures_creuses": "la nuit"}
    )
    assert res["errors"] == {"heures_creuses": "plages_invalides"}
    res = await hass.config_entries.flow.async_configure(res["flow_id"], SAISIE)
    assert res["type"] is FlowResultType.CREATE_ENTRY


async def test_deja_configure(hass: HomeAssistant):
    MockConfigEntry(domain=DOMAIN, unique_id=CAPTEUR, data={}).add_to_hass(hass)
    res = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    res = await hass.config_entries.flow.async_configure(res["flow_id"], SAISIE)
    assert res["type"] is FlowResultType.ABORT
    assert res["reason"] == "already_configured"


async def test_options(hass: HomeAssistant):
    entree = MockConfigEntry(
        domain=DOMAIN,
        unique_id=CAPTEUR,
        data={
            "entite_energie": CAPTEUR,
            "puissance": 6,
            "option_actuelle": "base",
            "heures_creuses": "22:00-06:00",
        },
    )
    entree.add_to_hass(hass)
    res = await hass.config_entries.options.async_init(entree.entry_id)
    assert res["type"] is FlowResultType.FORM
    res = await hass.config_entries.options.async_configure(
        res["flow_id"], {"puissance": "12", "option_actuelle": "hphc", "heures_creuses": "x"}
    )
    assert res["errors"] == {"heures_creuses": "plages_invalides"}
    res = await hass.config_entries.options.async_configure(
        res["flow_id"],
        {"puissance": "12", "option_actuelle": "hphc", "heures_creuses": "02:00-07:00,13:00-16:00"},
    )
    assert res["type"] is FlowResultType.CREATE_ENTRY
    assert entree.options == {
        "puissance": 12,
        "option_actuelle": "hphc",
        "heures_creuses": "02:00-07:00, 13:00-16:00",
        "index_hc": None,
        "index_hp": None,
    }


async def test_options_changement_de_plages(hass: HomeAssistant):
    """#369 : plages qui changent dans l'année, saisies avec leur date et réécrites proprement."""
    entree = MockConfigEntry(
        domain=DOMAIN,
        unique_id=CAPTEUR,
        data={
            "entite_energie": CAPTEUR,
            "puissance": 6,
            "option_actuelle": "hphc",
            "heures_creuses": "22:00-06:00",
        },
    )
    entree.add_to_hass(hass)
    res = await hass.config_entries.options.async_init(entree.entry_id)
    saisie = {"puissance": "6", "option_actuelle": "hphc"}
    res = await hass.config_entries.options.async_configure(
        res["flow_id"], {**saisie, "heures_creuses": "22h00-06h00 | 2026-02-30: 02:00-07:00"}
    )
    assert res["errors"] == {"heures_creuses": "plages_invalides"}
    res = await hass.config_entries.options.async_configure(
        res["flow_id"], {**saisie, "heures_creuses": "22h00-06h00|2026-03-15:02:00-07:00,13:00-16:00"}
    )
    assert res["type"] is FlowResultType.CREATE_ENTRY
    assert entree.options["heures_creuses"] == "22:00-06:00 | 2026-03-15: 02:00-07:00, 13:00-16:00"


INDEX = {"index_hc": "sensor.index_hc", "index_hp": "sensor.index_hp"}


@pytest.fixture
def _index(hass: HomeAssistant):
    for entite in INDEX.values():
        hass.states.async_set(entite, "1", {"unit_of_measurement": "kWh", "state_class": "total_increasing"})


@pytest.mark.usefixtures("_index")
@pytest.mark.parametrize(
    ("saisie", "erreurs"),
    [
        ({"index_hc": "sensor.index_hc"}, {"index_hp": "index_par_paire"}),
        ({"index_hp": "sensor.index_hp"}, {"index_hc": "index_par_paire"}),
        ({"index_hc": "sensor.index_hc", "index_hp": "sensor.index_hc"}, {"index_hp": "index_identiques"}),
        ({"index_hc": "sensor.absent", "index_hp": "sensor.index_hp"}, {"index_hc": "capteur_absent"}),
    ],
)
async def test_index_teleinformation_refuses(hass: HomeAssistant, saisie, erreurs):
    res = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    res = await hass.config_entries.flow.async_configure(res["flow_id"], {**SAISIE, **saisie})
    assert res["errors"] == erreurs


@pytest.mark.usefixtures("_index")
async def test_index_teleinformation_acceptes_puis_retires(hass: HomeAssistant):
    res = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    res = await hass.config_entries.flow.async_configure(res["flow_id"], {**SAISIE, **INDEX})
    assert res["type"] is FlowResultType.CREATE_ENTRY
    assert res["data"]["index_hc"] == "sensor.index_hc"
    assert res["data"]["index_hp"] == "sensor.index_hp"
    entree = hass.config_entries.async_get_entry(res["result"].entry_id)
    res = await hass.config_entries.options.async_init(entree.entry_id)
    res = await hass.config_entries.options.async_configure(
        res["flow_id"], {"puissance": "9", "option_actuelle": "base", "heures_creuses": "23:30-07:30"}
    )
    assert res["type"] is FlowResultType.CREATE_ENTRY
    assert entree.options["index_hc"] is None
    assert entree.options["index_hp"] is None
