"""tarifenergie : tarifs d'électricité comparés sur la consommation réelle de Home Assistant.

Chaque entrée suit un capteur d'énergie et compare, sur ses 12 derniers mois de
statistiques horaires, le coût TTC des tarifs réglementés (Base, Heures creuses)
publiés par la CRE et des offres de marché livrées dans ``offres/`` (issues #5 et #6),
chaque offre-option étant comparée séparément (#343).
Le calcul vit dans ``calcul.py``, ``modele.py`` et ``offres.py``, en Python pur.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import OPTIONS
from .coordinateur import CoordinateurTarifs, Referentiel
from .modele import Grilles
from .offres import grilles_offres, lire_offres
from .tempo import Climatologie, lire_couleurs

PLATFORMS: list[Platform] = [Platform.SENSOR]

type TarifenergieConfigEntry = ConfigEntry[CoordinateurTarifs]


def _charger() -> Referentiel:
    """Une entrée par offre-option (TRV Base, HP/HC, Tempo, puis chaque offre-option de marché),
    et l'historique réel des couleurs Tempo."""
    offres = lire_offres()
    grilles = {option: Grilles.charger(option) for option in OPTIONS}
    grilles.update(grilles_offres(offres))
    couleurs = lire_couleurs()
    return Referentiel(grilles, offres, couleurs, Climatologie.depuis(couleurs))


async def async_setup_entry(hass: HomeAssistant, entry: TarifenergieConfigEntry) -> bool:
    """Charge les grilles CRE (hors boucle), calcule une première fois, puis crée les capteurs."""
    referentiel = await hass.async_add_executor_job(_charger)
    coordinateur = CoordinateurTarifs(hass, entry, referentiel)
    await coordinateur.async_config_entry_first_refresh()
    entry.runtime_data = coordinateur
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TarifenergieConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
