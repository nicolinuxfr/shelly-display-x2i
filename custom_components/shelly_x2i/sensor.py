"""Sensor entities for Shelly X2i RPC diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ShellyX2iRPCRuntimeData
from .entity import ShellyX2iBaseEntity


def _sys_value(path: tuple[str, ...]) -> Callable[[dict], int | float | str | None]:
    """Build getter for nested sys_status value."""

    def _getter(sys_status: dict) -> int | float | str | None:
        value = sys_status
        for key in path:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        if isinstance(value, (int, float, str)):
            return value
        return None

    return _getter


@dataclass(frozen=True, kw_only=True)
class ShellyX2iSensorDescription(SensorEntityDescription):
    """Description for Shelly diagnostics sensor."""

    key: str
    value_fn: Callable[[dict], int | float | str | None]


SENSOR_DESCRIPTIONS: tuple[ShellyX2iSensorDescription, ...] = (
    ShellyX2iSensorDescription(
        key="uptime",
        translation_key="uptime",
        name="Uptime",
        icon="mdi:timer-outline",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_sys_value(("uptime",)),
    ),
    ShellyX2iSensorDescription(
        key="ram_free",
        translation_key="ram_free",
        name="Free RAM",
        icon="mdi:memory",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_sys_value(("ram_free",)),
    ),
    ShellyX2iSensorDescription(
        key="fs_free",
        translation_key="fs_free",
        name="Free Filesystem",
        icon="mdi:harddisk",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_sys_value(("fs_free",)),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up diagnostic sensors."""
    runtime: ShellyX2iRPCRuntimeData = entry.runtime_data
    entities = [
        ShellyX2iDiagnosticSensor(entry, runtime.coordinator, runtime.device_info, description)
        for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities, True)


class ShellyX2iDiagnosticSensor(ShellyX2iBaseEntity, SensorEntity):
    """Diagnostic sensor backed by Sys.GetStatus."""

    entity_description: ShellyX2iSensorDescription

    def __init__(self, entry, coordinator, fallback_device_info, description) -> None:
        super().__init__(
            entry=entry,
            coordinator=coordinator,
            fallback_device_info=fallback_device_info,
            key=description.key,
            name=description.name,
        )
        self.entity_description = description
        self._attr_translation_key = description.translation_key
        self._attr_icon = description.icon
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_entity_category = description.entity_category

    @property
    def native_value(self):
        """Return Sys.GetStatus value for this sensor."""
        sys_status = self.coordinator.data.get("sys_status")
        if not isinstance(sys_status, dict):
            return None
        return self.entity_description.value_fn(sys_status)
