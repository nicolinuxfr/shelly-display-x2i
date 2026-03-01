"""Number entities for Shelly X2i RPC."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import ShellyX2iRPCRuntimeData
from .entity import ShellyX2iBaseEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up number entities."""
    runtime: ShellyX2iRPCRuntimeData = entry.runtime_data
    async_add_entities([ShellyScreenBrightness(entry, runtime.coordinator, runtime.device_info)], True)


class ShellyScreenBrightness(ShellyX2iBaseEntity, NumberEntity, RestoreEntity):
    """Display brightness level."""

    _attr_translation_key = "screen_brightness"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = "slider"
    _attr_icon = "mdi:brightness-6"

    def __init__(self, entry, coordinator, fallback_device_info) -> None:
        super().__init__(
            entry=entry,
            coordinator=coordinator,
            fallback_device_info=fallback_device_info,
            key="screen_brightness",
            name="Brightness",
        )
        self._optimistic_value: float | None = None

    async def async_added_to_hass(self) -> None:
        """Restore last known value."""
        await super().async_added_to_hass()
        restored = await self.async_get_last_state()
        if restored is not None:
            try:
                self._optimistic_value = float(restored.state)
            except ValueError:
                self._optimistic_value = None

    @property
    def native_value(self) -> float | None:
        """Return the current brightness."""
        value = self.coordinator.data.get("brightness")
        if isinstance(value, (int, float)):
            return float(value)
        return self._optimistic_value

    async def async_set_native_value(self, value: float) -> None:
        """Set brightness through RPC."""
        level = int(round(value))
        await self.coordinator.client.call(
            "Ui.SetConfig",
            {
                "config": {
                    "brightness": {
                        "level": level,
                        "auto": False,
                    }
                }
            },
        )
        self._optimistic_value = float(level)
        await self.coordinator.async_request_refresh()
