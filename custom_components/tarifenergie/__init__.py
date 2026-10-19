"""tarifenergie : tarifs d'électricité comparés sur la consommation réelle de Home Assistant.

Chaque entrée suit un capteur d'énergie et compare, sur ses 12 derniers mois de
statistiques horaires, le coût TTC des tarifs réglementés (Base, Heures creuses)
publiés par la CRE. Le calcul vit dans ``calcul.py`` et ``modele.py``, en Python pur.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import OPTIONS
from .coordinateur import CoordinateurTarifs
from .modele import Grilles

PLATFORMS: list[Platform] = [Platform.SENSOR]

type TarifenergieConfigEntry = ConfigEntry[CoordinateurTarifs]


def _charger_grilles() -> dict[str, Grilles]:
    return {option: Grilles.charger(option) for option in OPTIONS}


async def async_setup_entry(hass: HomeAssistant, entry: TarifenergieConfigEntry) -> bool:
    """Charge les grilles CRE (hors boucle), calcule une première fois, puis crée les capteurs."""
    grilles = await hass.async_add_executor_job(_charger_grilles)
    coordinateur = CoordinateurTarifs(hass, entry, grilles)
    await coordinateur.async_config_entry_first_refresh()
    entry.runtime_data = coordinateur
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TarifenergieConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
