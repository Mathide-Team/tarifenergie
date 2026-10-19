"""Lecture de la consommation horaire réelle (statistiques du recorder) et comparaison des options."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .calcul import Comparaison, PlagesHC, comparer
from .const import (
    CONF_ENERGIE,
    CONF_HEURES_CREUSES,
    CONF_OPTION,
    CONF_PUISSANCE,
    CONF_TERRITOIRE,
    DOMAIN,
    FENETRE,
    INTERVALLE_MAJ,
    TERRITOIRE_PAR_DEFAUT,
)
from .modele import Grilles
from .offres import Offre, exclusions

_LOGGER = logging.getLogger(__name__)


def _lire_conso(hass: HomeAssistant, statistic_id: str, debut: datetime, fin: datetime) -> list:
    """Statistiques horaires « change » en kWh (exécuté dans le thread du recorder)."""
    lignes = statistics_during_period(
        hass,
        debut,
        fin,
        {statistic_id},
        "hour",
        {"energy": UnitOfEnergy.KILO_WATT_HOUR},
        {"change"},
    )
    return lignes.get(statistic_id, [])


async def async_conso_horaire(
    hass: HomeAssistant, statistic_id: str, debut: datetime, fin: datetime
) -> list[tuple[datetime, float]]:
    """Consommation par heure (début d'heure en heure locale, kWh), heures sans donnée omises.

    Une variation négative (compteur remis à zéro mal déclaré) est ignorée : elle
    fausserait le comparatif plus qu'elle ne l'éclaire.
    """
    lignes = await get_instance(hass).async_add_executor_job(_lire_conso, hass, statistic_id, debut, fin)
    conso: list[tuple[datetime, float]] = []
    for ligne in lignes:
        change = ligne.get("change")
        if change is None or change < 0:
            continue
        conso.append((dt_util.as_local(dt_util.utc_from_timestamp(ligne["start"])), float(change)))
    return conso


class CoordinateurTarifs(DataUpdateCoordinator[Comparaison]):
    """Recalcule toutes les 6 h le coût des 12 derniers mois pour chaque offre-option."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        grilles: dict[str, Grilles],
        offres: dict[str, Offre],
    ) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=f"{DOMAIN} {entry.title}", update_interval=INTERVALLE_MAJ
        )
        config = {**entry.data, **entry.options}
        self.grilles = grilles
        self.offres = offres
        self.territoire: str = config.get(CONF_TERRITOIRE, TERRITOIRE_PAR_DEFAUT)
        # Offres-options d'un autre territoire (ELD ou Enedis) : écartées avec la raison.
        self.exclues = exclusions(offres, self.territoire)
        self.entite: str = config[CONF_ENERGIE]
        self.puissance = int(config[CONF_PUISSANCE])
        self.option_actuelle: str = config[CONF_OPTION]
        self.plages = PlagesHC.lire(config[CONF_HEURES_CREUSES])
        self.debut: datetime | None = None
        self.fin: datetime | None = None

    async def _async_update_data(self) -> Comparaison:
        # Heures complètes uniquement : la dernière heure entamée n'a pas encore de statistique.
        fin = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        debut = fin - FENETRE
        conso = await async_conso_horaire(self.hass, self.entite, debut, fin)
        self.debut, self.fin = debut, fin
        return comparer(self.grilles, self.puissance, conso, self.plages, self.option_actuelle, self.exclues)
