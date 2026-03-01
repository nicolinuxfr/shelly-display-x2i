"""Base entity classes for Shelly X2i RPC integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.entity_registry import async_get
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SOURCE_DEVICE_ID, CONF_SOURCE_ENTITY_ID
from .coordinator import ShellyX2iRPCDataUpdateCoordinator


def _find_device_from_device_id(hass, device_id: str | None) -> DeviceEntry | None:
    """Resolve a device entry from a device_id."""
    if not device_id:
        return None
    dev_reg = dr.async_get(hass)
    return dev_reg.async_get(device_id)


def _find_device_from_entity_id(hass, entity_id: str | None) -> DeviceEntry | None:
    """Resolve a device entry from an entity_id."""
    if not entity_id:
        return None
    ent_reg = async_get(hass)
    if ent_reg is None:
        return None
    ent = ent_reg.async_get(entity_id)
    if ent is None or ent.device_id is None:
        return None
    dev_reg = dr.async_get(hass)
    return dev_reg.async_get(ent.device_id)


class ShellyX2iBaseEntity(CoordinatorEntity[ShellyX2iRPCDataUpdateCoordinator], Entity):
    """Common behavior for Shelly X2i entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: ShellyX2iRPCDataUpdateCoordinator,
        fallback_device_info: DeviceInfo,
        key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._source_device_id = (
            entry.options.get(CONF_SOURCE_DEVICE_ID)
            or entry.data.get(CONF_SOURCE_DEVICE_ID)
            or None
        )
        self._source_entity_id = (
            entry.options.get(CONF_SOURCE_ENTITY_ID)
            or entry.data.get(CONF_SOURCE_ENTITY_ID)
            or None
        )
        self._fallback_device_info = fallback_device_info
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self.device_entry: DeviceEntry | None = None

    async def async_added_to_hass(self) -> None:
        """Attach entities to an existing Shelly device when requested."""
        await super().async_added_to_hass()
        self.device_entry = _find_device_from_device_id(self.hass, self._source_device_id)
        if self.device_entry is None:
            self.device_entry = _find_device_from_entity_id(self.hass, self._source_entity_id)

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return fallback device metadata only when no linked device is used."""
        if self.device_entry is not None:
            return None
        return self._fallback_device_info
