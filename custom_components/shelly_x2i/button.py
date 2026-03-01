"""Button entities for Shelly X2i RPC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ShellyX2iRPCRuntimeData
from .entity import ShellyX2iBaseEntity


@dataclass(frozen=True, kw_only=True)
class ShellyX2iButtonDescription(ButtonEntityDescription):
    """Button description."""

    key: str
    name: str
    icon: str
    press_fn: Callable[["ShellyX2iButtonEntity"], Awaitable[Any]]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up button entities."""
    runtime: ShellyX2iRPCRuntimeData = entry.runtime_data

    descriptions = (
        ShellyX2iButtonDescription(
            key="refresh",
            name="Refresh",
            icon="mdi:refresh",
            press_fn=lambda entity: entity.coordinator.async_request_refresh(),
        ),
        ShellyX2iButtonDescription(
            key="reboot",
            name="Reboot",
            icon="mdi:restart",
            press_fn=lambda entity: entity.coordinator.client.call("Shelly.Reboot"),
        ),
    )
    entities = [
        ShellyX2iButtonEntity(entry, runtime.coordinator, runtime.device_info, description)
        for description in descriptions
    ]
    async_add_entities(entities, True)


class ShellyX2iButtonEntity(ShellyX2iBaseEntity, ButtonEntity):
    """Button backed by RPC action."""

    entity_description: ShellyX2iButtonDescription

    def __init__(self, entry, coordinator, fallback_device_info, description) -> None:
        super().__init__(
            entry=entry,
            coordinator=coordinator,
            fallback_device_info=fallback_device_info,
            key=description.key,
            name=description.name,
        )
        self.entity_description = description
        self._attr_icon = description.icon
        self._attr_translation_key = description.key

    async def async_press(self) -> None:
        """Press the button."""
        await self.entity_description.press_fn(self)
        await self.coordinator.async_request_refresh()
