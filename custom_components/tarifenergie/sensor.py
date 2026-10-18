"""Capteurs : coût de chaque option sur 12 mois, option la moins chère, économie possible."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TarifenergieConfigEntry
from .calcul import Comparaison
from .const import DOMAIN, OPTIONS
from .coordinateur import CoordinateurTarifs


@dataclass(frozen=True, kw_only=True)
class Description(SensorEntityDescription):
    valeur: Callable[[Comparaison], Any]
    attributs: Callable[[Comparaison, CoordinateurTarifs], dict[str, Any]] | None = None
    monetaire: bool = False


def _periode(comp: Comparaison, coord: CoordinateurTarifs) -> dict[str, Any]:
    return {
        "debut": coord.debut.isoformat() if coord.debut else None,
        "fin": coord.fin.isoformat() if coord.fin else None,
        "jours_couverts": comp.jours,
    }


def _cout(option: str) -> Description:
    def valeur(comp: Comparaison) -> Decimal | None:
        cout = comp.couts.get(option)
        return cout.total if cout else None

    def attributs(comp: Comparaison, coord: CoordinateurTarifs) -> dict[str, Any]:
        cout = comp.couts.get(option)
        detail = cout.arrondi() if cout else {"indisponible": comp.indisponibles.get(option)}
        detail.pop("option", None)
        detail.pop("total", None)
        return {**detail, **_periode(comp, coord)}

    return Description(
        key=f"cout_{option}",
        translation_key=f"cout_{option}",
        valeur=valeur,
        attributs=attributs,
        monetaire=True,
    )


def _classement(comp: Comparaison, coord: CoordinateurTarifs) -> dict[str, Any]:
    return {
        "classement": [{"option": c.option, "total": float(c.total)} for c in comp.classement],
        "option_actuelle": comp.option_actuelle,
        "indisponibles": comp.indisponibles,
        **_periode(comp, coord),
    }


DESCRIPTIONS: tuple[Description, ...] = (
    *(_cout(option) for option in OPTIONS),
    Description(
        key="option_moins_chere",
        translation_key="option_moins_chere",
        device_class=SensorDeviceClass.ENUM,
        options=list(OPTIONS),
        valeur=lambda comp: comp.moins_chere.option if comp.moins_chere else None,
        attributs=_classement,
    ),
    Description(
        key="economie_possible",
        translation_key="economie_possible",
        valeur=lambda comp: comp.economie,
        attributs=_classement,
        monetaire=True,
    ),
    Description(
        key="consommation",
        translation_key="consommation",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=0,
        valeur=lambda comp: (
            round(float(sum(next(iter(comp.couts.values())).kwh.values())), 3) if comp.couts else None
        ),
        attributs=lambda comp, coord: _periode(comp, coord),
    ),
    Description(
        key="part_heures_creuses",
        translation_key="part_heures_creuses",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        valeur=lambda comp: _part_hc(comp),
    ),
)


def _part_hc(comp: Comparaison) -> float | None:
    cout = comp.couts.get("hphc")
    if cout is None:
        return None
    total = sum(cout.kwh.values())
    return round(float(cout.kwh.get("hc", 0) / total * 100), 2) if total else None


async def async_setup_entry(
    hass: HomeAssistant, entry: TarifenergieConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(CapteurTarif(entry.runtime_data, entry, d) for d in DESCRIPTIONS)


class CapteurTarif(CoordinatorEntity[CoordinateurTarifs], SensorEntity):
    """Une valeur de la comparaison."""

    _attr_has_entity_name = True
    entity_description: Description

    def __init__(
        self, coord: CoordinateurTarifs, entry: TarifenergieConfigEntry, description: Description
    ) -> None:
        super().__init__(coord)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="CRE (tarifs réglementés)",
            model="Comparaison sur 12 mois",
        )
        if description.monetaire:
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_native_unit_of_measurement = coord.hass.config.currency
            self._attr_suggested_display_precision = 2

    @property
    def native_value(self) -> Any:
        return self.entity_description.valeur(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributs is None:
            return None
        return self.entity_description.attributs(self.coordinator.data, self.coordinator)
