"""Switch entities for Shelly X2i RPC."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import ShellyX2iRPCRuntimeData
from .client import ShellyRPCError
from .entity import ShellyX2iBaseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up switch entities."""
    runtime: ShellyX2iRPCRuntimeData = entry.runtime_data
    async_add_entities(
        [ShellyScreenPowerSwitch(entry, runtime.coordinator, runtime.device_info)],
        True,
    )


class ShellyScreenPowerSwitch(ShellyX2iBaseEntity, SwitchEntity, RestoreEntity):
    """Power state of the X2i display."""

    _attr_translation_key = "screen_power"
    _attr_icon = "mdi:monitor"

    def __init__(self, entry, coordinator, fallback_device_info) -> None:
        super().__init__(
            entry=entry,
            coordinator=coordinator,
            fallback_device_info=fallback_device_info,
            key="screen_power",
            name="Screen",
        )
        self._optimistic_state: bool | None = None

    async def async_added_to_hass(self) -> None:
        """Restore last known state."""
        await super().async_added_to_hass()
        restored = await self.async_get_last_state()
        if restored is not None:
            self._optimistic_state = restored.state == "on"

    @property
    def is_on(self) -> bool | None:
        """Return current power status."""
        state = self.coordinator.data.get("screen_on")
        if isinstance(state, bool):
            return state
        expected = self.coordinator.expected_screen_on
        if isinstance(expected, bool):
            return expected
        if isinstance(self._optimistic_state, bool):
            return self._optimistic_state
        # Keep a deterministic toggle state even when the firmware does not
        # expose screen status in Ui.GetStatus.
        return False

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the screen on."""
        self._optimistic_state = True
        self.coordinator.set_expected_screen_on(True)
        self.async_write_ha_state()
        pending_level = self.coordinator.pending_brightness_level
        self.hass.async_create_task(self._async_send_power_command(True, pending_level))

    async def _async_send_power_command(self, on: bool, pending_level: int | None) -> None:
        """Send screen power command without blocking the UI interaction path."""
        try:
            _LOGGER.debug("Sending Ui.Screen.Set on=%s", on)
            await self.coordinator.client.call("Ui.Screen.Set", {"on": on})
            _LOGGER.debug("Ui.Screen.Set done on=%s", on)
            if on and isinstance(pending_level, int) and pending_level > 0:
                _LOGGER.debug("Restoring brightness level=%s after power on", pending_level)
                await self.coordinator.client.call(
                    "Ui.SetConfig",
                    {
                        "config": {
                            "brightness": {
                                "level": pending_level,
                                "auto": False,
                            }
                        }
                    },
                )
                self.coordinator.clear_pending_brightness_level()
            self.hass.async_create_task(self.coordinator.async_request_refresh())
        except ShellyRPCError as err:
            _LOGGER.warning("Failed setting screen power to %s: %s", on, err)
            # Revert optimistic state only if command failed.
            self._optimistic_state = not on
            self.coordinator.set_expected_screen_on(not on)
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the screen off."""
        # Preserve the most recent explicit user target if one is already pending.
        current_pending = self.coordinator.pending_brightness_level
        if not isinstance(current_pending, int) or current_pending <= 0:
            current = self.coordinator.data.get("brightness_config")
            if not isinstance(current, (int, float)):
                current = self.coordinator.data.get("brightness")
            if not isinstance(current, (int, float)):
                current = self.coordinator.last_nonzero_brightness_level
            if isinstance(current, (int, float)) and int(round(float(current))) > 0:
                self.coordinator.set_pending_brightness_level(int(round(float(current))))

        self._optimistic_state = False
        self.coordinator.set_expected_screen_on(False)
        self.async_write_ha_state()
        self.hass.async_create_task(self._async_send_power_command(False, None))
