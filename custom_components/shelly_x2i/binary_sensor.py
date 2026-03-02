"""Binary sensor entities for Shelly X2i RPC diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ShellyX2iRPCRuntimeData
from .entity import ShellyX2iBaseEntity


def _restart_required(sys_status: dict) -> bool | None:
    value = sys_status.get("restart_required")
    return value if isinstance(value, bool) else None


def _updates_available(sys_status: dict) -> bool:
    updates = sys_status.get("available_updates")
    if not isinstance(updates, dict):
        return False
    return any(isinstance(v, dict) and bool(v) for v in updates.values())


@dataclass(frozen=True, kw_only=True)
class ShellyX2iBinarySensorDescription(BinarySensorEntityDescription):
    """Description for Shelly diagnostics binary sensor."""

    key: str
    is_on_fn: Callable[[dict], bool | None]


BINARY_SENSOR_DESCRIPTIONS: tuple[ShellyX2iBinarySensorDescription, ...] = (
    ShellyX2iBinarySensorDescription(
        key="restart_required",
        translation_key="restart_required",
        name="Restart Required",
        icon="mdi:restart-alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=_restart_required,
    ),
    ShellyX2iBinarySensorDescription(
        key="updates_available",
        translation_key="updates_available",
        name="Updates Available",
        icon="mdi:update",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=_updates_available,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up diagnostic binary sensors."""
    runtime: ShellyX2iRPCRuntimeData = entry.runtime_data
    entities = [
        ShellyX2iDiagnosticBinarySensor(entry, runtime.coordinator, runtime.device_info, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities, True)


class ShellyX2iDiagnosticBinarySensor(ShellyX2iBaseEntity, BinarySensorEntity):
    """Diagnostic binary sensor backed by Sys.GetStatus."""

    entity_description: ShellyX2iBinarySensorDescription

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
        self._attr_entity_category = description.entity_category

    @property
    def is_on(self) -> bool | None:
        """Return Sys.GetStatus bool value for this sensor."""
        sys_status = self.coordinator.data.get("sys_status")
        if not isinstance(sys_status, dict):
            return None
        return self.entity_description.is_on_fn(sys_status)
