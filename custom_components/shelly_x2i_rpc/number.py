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

_SHELLY_BRIGHTNESS_MAX = 250


def _raw_to_percent(raw_level: float) -> float:
    """Convert Shelly brightness level (0..250) to Home Assistant percentage."""
    clamped = max(0.0, min(float(_SHELLY_BRIGHTNESS_MAX), raw_level))
    return round((clamped / float(_SHELLY_BRIGHTNESS_MAX)) * 100.0, 1)


def _percent_to_raw(percent: float) -> int:
    """Convert Home Assistant percentage (0..100) to Shelly brightness level."""
    clamped = max(0.0, min(100.0, percent))
    return int(round((clamped / 100.0) * float(_SHELLY_BRIGHTNESS_MAX)))


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
                restored_value = float(restored.state)
                if restored_value > 100.0:
                    # Backward compatibility with old states stored as raw
                    # Shelly brightness levels (0..250).
                    restored_value = _raw_to_percent(restored_value)
                self._optimistic_value = max(0.0, min(100.0, restored_value))
            except ValueError:
                self._optimistic_value = None

    @property
    def native_value(self) -> float | None:
        """Return the current brightness."""
        raw_value = self.coordinator.data.get("brightness")
        if isinstance(raw_value, (int, float)):
            return _raw_to_percent(float(raw_value))
        return self._optimistic_value

    async def async_set_native_value(self, value: float) -> None:
        """Set brightness through RPC."""
        level = _percent_to_raw(float(value))
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
        self._optimistic_value = max(0.0, min(100.0, float(value)))
        await self.coordinator.async_request_refresh()
