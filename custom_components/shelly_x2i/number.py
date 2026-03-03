"""Number entities for Shelly X2i RPC."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import ShellyX2iRPCRuntimeData
from .entity import ShellyX2iBaseEntity

_LOGGER = logging.getLogger(__name__)


def _raw_to_percent(raw_level: float) -> int:
    """Clamp a firmware brightness level (0..100) to an integer percentage.

    The X2i firmware stores brightness as a percentage in both GetConfig/GetStatus
    and SetConfig, so no unit conversion is needed here.
    """
    return int(round(max(0.0, min(100.0, raw_level))))


def _percent_to_raw(percent: float) -> int:
    """Convert Home Assistant percentage (0..100) to Shelly write level."""
    return int(round(max(0.0, min(100.0, percent))))


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
        self._optimistic_value: int | None = None

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
                self._optimistic_value = int(round(max(0.0, min(100.0, restored_value))))
            except ValueError:
                self._optimistic_value = None

    @property
    def native_value(self) -> int | None:
        """Return the current brightness."""
        raw_value = self.coordinator.data.get("brightness")
        raw_status = self.coordinator.data.get("brightness_status")
        raw_config = self.coordinator.data.get("brightness_config")
        screen_is_on = self.coordinator.data.get("screen_on")
        effective_screen_on = (
            screen_is_on if isinstance(screen_is_on, bool) else self.coordinator.expected_screen_on
        )

        if effective_screen_on is False:
            pending_level = self.coordinator.pending_brightness_level
            if isinstance(pending_level, int):
                return pending_level
            if isinstance(raw_config, (int, float)):
                return _raw_to_percent(float(raw_config))
            last_nonzero = self.coordinator.last_nonzero_brightness_level
            if isinstance(last_nonzero, int):
                return _raw_to_percent(float(last_nonzero))

        if effective_screen_on is None:
            if isinstance(raw_status, (int, float)) and isinstance(raw_config, (int, float)):
                # Firmware can report status=0 while the panel is "off" but keep
                # a non-zero configured brightness level.
                if int(round(float(raw_status))) == 0 and float(raw_config) > 0:
                    return _raw_to_percent(float(raw_config))

        if isinstance(raw_status, (int, float)):
            return _raw_to_percent(float(raw_status))
        if isinstance(raw_config, (int, float)):
            return _raw_to_percent(float(raw_config))
        if isinstance(raw_value, (int, float)):
            return _raw_to_percent(float(raw_value))
        return self._optimistic_value

    async def async_set_native_value(self, value: float) -> None:
        """Set brightness through RPC."""
        target_percent = max(0.0, min(100.0, float(value)))
        level = _percent_to_raw(target_percent)
        target_percent_int = int(round(target_percent))
        # Keep desired brightness until coordinator confirms device applied it.
        self.coordinator.set_pending_brightness_level(level)
        screen_is_on = self.coordinator.data.get("screen_on")
        effective_screen_on = (
            screen_is_on if isinstance(screen_is_on, bool) else self.coordinator.expected_screen_on
        )

        if effective_screen_on is False:
            # Keep brightness independent from power: remember target while off,
            # then apply it when the screen is turned on.
            _LOGGER.debug("Brightness set while OFF -> pending level=%s (%s%%)", level, target_percent)
            self.coordinator.set_pending_brightness_level(level)
            self._optimistic_value = target_percent_int
            self.async_write_ha_state()
            return

        _LOGGER.debug("Brightness set live -> level=%s (%s%%)", level, target_percent)
        self.coordinator.set_expected_screen_on(True)
        await self.coordinator.async_set_brightness_level(level)
        self._optimistic_value = target_percent_int
        await self.coordinator.async_request_refresh()
