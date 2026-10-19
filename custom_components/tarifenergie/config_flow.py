"""Configuration depuis l'interface (issue #2).

Une étape : capteur d'énergie (statistiques en kWh), puissance souscrite, option
actuelle et plages d'heures creuses du compteur. Les options permettent de changer
tout sauf le capteur. Une entrée par capteur.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .calendrier import PlagesDatees, PlagesInvalides
from .const import (
    CONF_ENERGIE,
    CONF_HEURES_CREUSES,
    CONF_NOM,
    CONF_OPTION,
    CONF_PUISSANCE,
    DOMAIN,
    HEURES_CREUSES_PAR_DEFAUT,
    NOM_PAR_DEFAUT,
    OPTIONS,
    PUISSANCES,
)

STATE_CLASSES = {SensorStateClass.TOTAL, SensorStateClass.TOTAL_INCREASING}
UNITES = {u.value for u in UnitOfEnergy}


def _verifier_capteur(hass: HomeAssistant, entity_id: str) -> str | None:
    """Code d'erreur si le capteur ne fournit pas de statistiques d'énergie cumulée."""
    etat = hass.states.get(entity_id)
    if etat is None:
        return "capteur_absent"
    if etat.attributes.get(ATTR_UNIT_OF_MEASUREMENT) not in UNITES:
        return "unite"
    if etat.attributes.get("state_class") not in STATE_CLASSES:
        return "state_class"
    return None


def _schema_contrat(valeurs: dict[str, Any]) -> dict[vol.Marker, Any]:
    return {
        vol.Required(CONF_PUISSANCE, default=str(valeurs.get(CONF_PUISSANCE, 6))): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[str(p) for p in PUISSANCES],
                mode=selector.SelectSelectorMode.DROPDOWN,
                translation_key="puissance",
            )
        ),
        vol.Required(CONF_OPTION, default=valeurs.get(CONF_OPTION, OPTIONS[0])): selector.SelectSelector(
            selector.SelectSelectorConfig(options=list(OPTIONS), translation_key="option")
        ),
        vol.Required(
            CONF_HEURES_CREUSES, default=valeurs.get(CONF_HEURES_CREUSES, HEURES_CREUSES_PAR_DEFAUT)
        ): selector.TextSelector(),
    }


def _verifier_contrat(saisie: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Normalise la saisie (puissance en entier, plages réécrites) ; erreurs par champ."""
    try:
        plages = PlagesDatees.lire(saisie[CONF_HEURES_CREUSES])
    except PlagesInvalides:
        return saisie, {CONF_HEURES_CREUSES: "plages_invalides"}
    return {**saisie, CONF_PUISSANCE: int(saisie[CONF_PUISSANCE]), CONF_HEURES_CREUSES: plages.texte()}, {}


class TarifenergieConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ajout d'un compteur d'électricité."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        erreurs: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_ENERGIE])
            self._abort_if_unique_id_configured()
            if code := _verifier_capteur(self.hass, user_input[CONF_ENERGIE]):
                erreurs[CONF_ENERGIE] = code
            else:
                donnees, erreurs = _verifier_contrat(user_input)
                if not erreurs:
                    return self.async_create_entry(title=donnees.pop(CONF_NOM), data=donnees)
        valeurs = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NOM, default=valeurs.get(CONF_NOM, NOM_PAR_DEFAUT)
                ): selector.TextSelector(),
                vol.Required(CONF_ENERGIE, default=valeurs.get(CONF_ENERGIE, vol.UNDEFINED)): (
                    selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.ENERGY)
                    )
                ),
                **_schema_contrat(valeurs),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=erreurs)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TarifenergieOptionsFlow:
        return TarifenergieOptionsFlow()


class TarifenergieOptionsFlow(OptionsFlowWithReload):
    """Changement de puissance, d'option ou d'heures creuses (recharge l'entrée)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        erreurs: dict[str, str] = {}
        if user_input is not None:
            donnees, erreurs = _verifier_contrat(user_input)
            if not erreurs:
                return self.async_create_entry(data=donnees)
        valeurs = user_input or {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(_schema_contrat(valeurs)), errors=erreurs
        )
